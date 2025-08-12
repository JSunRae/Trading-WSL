from sys import path

path.append("..")

from src.infra.contract_factories import stock
from src.types.project_types import Symbol

import MasterPy_Trading as MPT
import asyncio
from typing import Optional

# from atexit import register as atexit_register


def Add_Level2(symbol: str) -> None:
    CanAdd_Level2 = True

    if len(Dict_Level2) == 3:
        CanAdd_Level2 = False

        print("Already 3 Market Depth running, stop one:")
        for i, key in enumerate(Dict_Level2):
            if i + 1 == 3:
                print(f" {i + 1} - {key},", end="")
            else:
                print(f" {i + 1} - {key}")
        Question = input("?")
        keys_to_delete = [
            key for i, key in enumerate(Dict_Level2) if str(i + 1) == Question
        ]
        for key in keys_to_delete:
            Dict_Level2[
                key
            ].cancelMktDepth()  # Don't forget to add the parentheses here.
            del Dict_Level2[key]

    if CanAdd_Level2:
        contract = stock(Symbol(symbol))
        Dict_Level2["L2_" + symbol] = MPT.MarketDepthCls(ib, contract)
        print(f"{symbol} added to stream")
    else:
        print(f"{symbol} NOT added to stream")

def Close_Level2(cancel_all: Optional[bool] = None) -> None:
    if cancel_all is None:
        user_input = input("Do you want to cancel all?")
        cancel_all = (user_input[0].lower() == "y") if user_input else False

    if cancel_all:
        for key in list(Dict_Level2.keys()):
            Dict_Level2[key].cancelMktDepth()
            del Dict_Level2[key]
    else:
        print("Which symbol do you want to cancel:")
        for i, key in enumerate(Dict_Level2):
            if i + 1 == 3:
                print(f" {i + 1} - {key},", end="")
            else:
                print(f" {i + 1} - {key}")
        Question = input("?")
        for i, key in enumerate(list(Dict_Level2.keys())):
            if Question == str(i + 1):
                Dict_Level2[key].cancelMktDepth()
                del Dict_Level2[key]
                del Dict_Level2[key]


if __name__ == "__main__":
    # TainList = pd.read_csv("./Train List_FINAL.csv", header=0)
    ib, Req = asyncio.run(MPT.InitiateTWS(LiveMode=False))
    Dict_Level2 = {}
    for symbol in ["PHUN"]:  # , "ANGH", "ATOS"]:  # max 3
        Add_Level2(symbol)

    # Ticker_AllLast = ib.reqTickByTickData(contract, tickType='AllLast', numberOfTicks=0, ignoreSize=False)
    # TikBTik = MPT.TickByTickCls(ib, contract)
    # MkDpth = MPT.MarketDepthCls(ib, contract)

    LoopNow = True
    while LoopNow:
        try:
            ib.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            Question = input("Add Stock to Level 2 stream?")
            if Question[0].lower() == "y":
                symbol = input("Which symbol do you want to add?").upper()
                Add_Level2(symbol)
                continue
            Question = input("Cancel Stock from Level 2 stream?")
            if Question[0].lower() == "y":
                LoopNow = False

    print("Complete")

print("ibMain has ended or completed")
