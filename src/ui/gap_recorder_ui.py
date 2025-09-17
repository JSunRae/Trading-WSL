"""Minimal Tkinter UI wiring scanner -> table -> session manager (skeleton)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Iterable
from datetime import datetime
from tkinter import ttk
from typing import Any, cast

from src.config import extensions as cfg_ext
from src.recording.l2_slot_manager import L2SlotManager
from src.recording.session_manager import SessionManager
from src.scanner.etf_blacklist import load_etf_blacklist
from src.scanner.gap_rvol_scanner import Candidate, GapRvolScanner
from src.scanner.ib_market_scanner import IBMarketScanner
from src.services.market_data.market_data_service import (  # type: ignore
    IB as MD_IB,
)
from src.services.market_data.market_data_service import (
    MarketDataService,
)
from src.utils.time_utils import format_ts

REFRESH_INTERVAL_MS = cfg_ext.refresh_seconds() * 1000


class App:
    ib: Any | None
    scanner: GapRvolScanner
    ib_scanner: IBMarketScanner
    market_data_service: MarketDataService
    session_mgr: SessionManager
    event_q: queue.Queue[tuple[str, Any]]
    _hidden: set[str]
    _etf_blacklist: set[str]

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Gap Recorder")
        # Establish IB connection (synchronous helper)
        try:
            from src.utils.ib_connection_helper import get_ib_connection_sync

            self.ib, _tracker = get_ib_connection_sync(live_mode=False)
        except Exception:  # noqa: BLE001
            # Fallback to uninitialized/None; avoid constructing Protocols at runtime
            self.ib = None  # type: ignore[assignment]
        # Core scanner components
        self.scanner = GapRvolScanner(None)
        self.ib_scanner = IBMarketScanner(self.ib)

        # Pass IB to MarketDataService – if unavailable, use a NullIB stub
        class NullIB:
            def isConnected(self) -> bool:  # noqa: N802
                return False

            def qualifyContracts(self, *_args: Any, **_kwargs: Any) -> Any:  # noqa: N802
                return None

            def reqMktDepth(self, *_args: Any, **_kwargs: Any) -> Any:  # noqa: N802
                return None

            def cancelMktDepth(self, *_args: Any, **_kwargs: Any) -> Any:  # noqa: N802
                return None

            def reqTickByTickData(self, *_args: Any, **_kwargs: Any) -> Any:  # noqa: N802
                return None

            def cancelTickByTickData(self, *_args: Any, **_kwargs: Any) -> Any:  # noqa: N802
                return None

        md_ib_any = self.ib if self.ib is not None else NullIB()
        self.market_data_service = MarketDataService(cast(MD_IB, md_ib_any))
        self.session_mgr = SessionManager(self.market_data_service, L2SlotManager())
        # Runtime state
        self.event_q = queue.Queue()
        self._hidden = set()
        self._etf_blacklist = load_etf_blacklist(cfg_ext.etf_blacklist_file())
        # Build UI & load persisted state
        self._build_ui()
        self._load_state()
        # Timers
        self._schedule_scan(initial=True)
        self._schedule_upgrade()

    def _build_ui(self):
        top = ttk.Frame(self.root)
        top.pack(fill="x")
        self.min_gap_var = tk.DoubleVar(value=cfg_ext.min_gap_pct())
        self.min_rvol_var = tk.DoubleVar(value=cfg_ext.min_rvol())
        ttk.Label(top, text="Min Gap %").pack(side="left")
        ttk.Entry(top, width=5, textvariable=self.min_gap_var).pack(side="left")
        ttk.Label(top, text="Min RVOL").pack(side="left")
        ttk.Entry(top, width=5, textvariable=self.min_rvol_var).pack(side="left")
        self.refresh_var = tk.IntVar(value=cfg_ext.refresh_seconds())
        ttk.Label(top, text="Refresh(s)").pack(side="left")
        ttk.Entry(top, width=5, textvariable=self.refresh_var).pack(side="left")
        self.exclude_etf_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            top,
            text="Exclude ETFs",
            variable=self.exclude_etf_var,
            command=self.manual_refresh,
        ).pack(side="left")
        ttk.Button(top, text="Refresh Now", command=self.manual_refresh).pack(
            side="left"
        )
        ttk.Button(top, text="Start Selected", command=self.start_selected).pack(
            side="left"
        )
        ttk.Button(top, text="Stop Selected", command=self.stop_selected).pack(
            side="left"
        )
        ttk.Button(top, text="Stop All", command=self.stop_all).pack(side="left")
        ttk.Label(top, text="Price bound: $1–$30").pack(side="right")

        self.tree = ttk.Treeview(
            self.root,
            columns=(
                "Symbol",
                "Last",
                "Gap%",
                "PrevClose",
                "CumVol",
                "ADV20",
                "RVOL",
                "Exchange",
                "Status",
                "Updated",
            ),
            show="headings",
            height=18,
        )
        for c in self.tree.cget("columns"):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=80, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Button-3>", self._context_menu)

        self.status_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status_var, anchor="w").pack(fill="x")

    def _context_menu(self, event: tk.Event):  # type: ignore[type-arg]
        item = self.tree.identify_row(event.y)
        if not item:
            return
        sym = self.tree.set(item, "Symbol")
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label=f"Hide {sym}", command=lambda: self._hide_symbol(sym))
        menu.post(event.x_root, event.y_root)

    def _hide_symbol(self, sym: str) -> None:
        self._hidden.add(sym.upper())
        self._refresh_table([])  # remove now

    def manual_refresh(self) -> None:
        self._schedule_scan(force=True)

    def _schedule_scan(self, initial: bool = False, force: bool = False) -> None:
        interval = self.refresh_var.get() if not initial else cfg_ext.refresh_seconds()
        self.root.after(
            100 if (initial or force) else interval * 1000, self._launch_scan_thread
        )

    def _launch_scan_thread(self) -> None:
        t = threading.Thread(target=self._scan_worker, daemon=True)
        t.start()

    def _scan_worker(self) -> None:
        """Background thread: fetch universe -> compute gap/RVOL -> filter -> queue UI update."""
        try:
            universe = self.ib_scanner.fetch_universe(max_symbols=200)
            # Defensive price bound filter again (server-side already attempts this)
            price_min, price_max = cfg_ext.price_min(), cfg_ext.price_max()
            cands = self.scanner.scan(universe)
            mg = self.min_gap_var.get()
            mr = self.min_rvol_var.get()
            filtered: list[Candidate] = []
            for c in cands:
                if (
                    c.gap_pct * 100 >= mg
                    and c.rvol >= mr
                    and price_min <= c.last <= price_max
                    and c.symbol not in self._hidden
                    and (
                        not self.exclude_etf_var.get()
                        or c.symbol not in self._etf_blacklist
                    )
                ):
                    filtered.append(c)
            self.event_q.put(("scan_result", filtered))
        except Exception as e:  # noqa: BLE001
            self.event_q.put(("error", str(e)))
        finally:
            self._schedule_scan()

    def process_events(self) -> None:
        """Poll event queue (UI thread safe) and update UI/state."""
        try:
            while True:
                evt, payload = self.event_q.get_nowait()
                if evt == "scan_result":
                    self._refresh_table(payload)
                elif evt == "error":
                    # Non-intrusive error display
                    self.status_var.set(f"Last error: {payload}")
        except queue.Empty:
            pass
        # Promotion attempt (lightweight) every cycle for responsiveness
        self.session_mgr.upgrade_cycle()
        self.root.after(250, self.process_events)

    def _refresh_table(self, candidates: Iterable[Candidate]) -> None:
        existing = set(self.tree.get_children())
        iid_by_sym: dict[str, str] = {
            self.tree.set(iid, "Symbol"): iid for iid in existing
        }
        keep: set[str] = set()
        cand_list = list(candidates)
        for c in cand_list:
            iid = iid_by_sym.get(c.symbol)
            values = [
                c.symbol,
                f"{c.last:.2f}",
                f"{c.gap_pct * 100:.2f}",
                f"{c.prev_close:.2f}",
                c.cum_volume,
                c.adv20,
                f"{c.rvol:.2f}",
                c.exchange,
                self._session_status(c.symbol),
                format_ts(c.updated),
            ]
            if iid:
                self.tree.item(iid, values=values)
                row_iid: str = iid
            else:
                row_iid = self.tree.insert("", "end", values=values)
            keep.add(row_iid)
        for iid in existing - keep:
            self.tree.delete(iid)
        summary = self.session_mgr.active_summary()
        size = len(cand_list)
        self.status_var.set(
            f"Last: {datetime.now().strftime('%H:%M:%S')} Candidates: {size} Active ticks {summary['ticks']} / L2 {summary['l2']} ({summary['l2']}/5) Queue {summary['queued']} Hidden {len(self._hidden)} ETFs {'ON' if self.exclude_etf_var.get() else 'OFF'}"
        )

    def _session_status(self, sym: str) -> str:
        for s in self.session_mgr.list_sessions():
            if s.symbol == sym:
                if s.mode == "l2":
                    return "L2"
                if s.mode == "queued":
                    return "Queued"
                return "Tick"
        return "Idle"

    def start_selected(self) -> None:
        sels = self.tree.selection()
        for iid in sels:
            sym = self.tree.set(iid, "Symbol")
            self.session_mgr.start(sym)
        self.session_mgr.upgrade_cycle()
        self._refresh_table([])

    def stop_selected(self) -> None:
        sels = self.tree.selection()
        for iid in sels:
            sym = self.tree.set(iid, "Symbol")
            self.session_mgr.stop(sym)
        self.session_mgr.upgrade_cycle()
        self._refresh_table([])

    def stop_all(self) -> None:
        self.session_mgr.stop_all()
        self._refresh_table([])

    # ------------------------------------------------------------------
    # Promotion cycle timer
    # ------------------------------------------------------------------
    def _schedule_upgrade(self) -> None:
        self.session_mgr.upgrade_cycle()
        self.root.after(2000, self._schedule_upgrade)

    # ------------------------------------------------------------------
    # State persistence (simple wiring – integrates state_store)
    # ------------------------------------------------------------------
    def _collect_state(self) -> dict[str, Any]:
        prefs = {
            "min_gap_pct": self.min_gap_var.get(),
            "min_rvol": self.min_rvol_var.get(),
            "refresh_sec": self.refresh_var.get(),
            "exclude_etfs": self.exclude_etf_var.get(),
        }
        sessions = [
            {
                "symbol": s.symbol,
                "mode": s.mode,
                "queued": s.mode == "queued",
                "start_time": getattr(s, "start_time", ""),
            }
            for s in self.session_mgr.list_sessions()
        ]
        return {
            "preferences": prefs,
            "hidden_symbols": list(self._hidden),
            "sessions": sessions,
        }

    def _load_state(self) -> None:
        from src.persistence.state_store import StateStore

        store = StateStore()
        st = store.load()
        if not st:
            return
        try:
            self.min_gap_var.set(
                st.preferences.get("min_gap_pct", self.min_gap_var.get())
            )
            self.min_rvol_var.set(
                st.preferences.get("min_rvol", self.min_rvol_var.get())
            )
            self.refresh_var.set(
                st.preferences.get("refresh_sec", self.refresh_var.get())
            )
            if "exclude_etfs" in st.preferences:
                self.exclude_etf_var.set(bool(st.preferences.get("exclude_etfs")))
            self._hidden = {s.upper() for s in st.hidden_symbols}
            for sess in st.sessions:
                # only restore tick sessions initially; promotions handled by upgrade cycle
                self.session_mgr.start(sess.symbol)
        except Exception:
            pass

    def _save_state(self) -> None:
        from src.persistence.state_store import AppState, SessionState, StateStore

        data = self._collect_state()
        sessions = [
            SessionState(
                symbol=s["symbol"],
                mode=s["mode"],
                start_time=s.get("start_time", ""),
                queued=s.get("queued", False),
            )
            for s in data["sessions"]
        ]
        app_state = AppState(
            sessions=sessions,
            hidden_symbols=data["hidden_symbols"],
            preferences=data["preferences"],
        )
        store = StateStore()
        store.save(app_state)

    def on_close(self) -> None:
        try:
            self._save_state()
            self.session_mgr.stop_all()
        finally:
            self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    app.process_events()
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
