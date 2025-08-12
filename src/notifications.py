#!/usr/bin/env python3
"""
Cross-platform notification system for trading alerts

This module provides notification functionality that works across Windows and Linux/WSL.
It replaces the Windows-specific WhatsApp.py functionality with more robust alternatives.
"""

import logging
import subprocess
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NotificationManager:
    """Cross-platform notification manager for trading system"""

    def __init__(self):
        self.platform = sys.platform
        self.is_windows = self.platform == "win32"
        self.is_linux = self.platform.startswith("linux")

    def send_desktop_notification(self, title: str, message: str) -> bool:
        """Send a desktop notification (cross-platform)"""
        try:
            if self.is_windows:
                return self._send_windows_notification(title, message)
            elif self.is_linux:
                return self._send_linux_notification(title, message)
            else:
                logger.warning(
                    f"Desktop notifications not supported on {self.platform}"
                )
                return False
        except Exception as e:
            logger.error(f"Failed to send desktop notification: {e}")
            return False

    def _send_windows_notification(self, title: str, message: str) -> bool:
        """Send Windows toast notification"""
        try:
            # Try using plyer first (cross-platform library)
            try:
                from plyer import notification

                notification.notify(
                    title=title, message=message, app_name="Trading System", timeout=10
                )
                logger.info("Desktop notification sent via plyer")
                return True
            except ImportError:
                logger.debug("plyer not available, trying PowerShell fallback")
            except Exception as e:
                logger.warning(f"plyer notification failed: {e}, trying fallback")

            # Fallback to PowerShell
            ps_script = f'''
            Add-Type -AssemblyName System.Windows.Forms
            $notification = New-Object System.Windows.Forms.NotifyIcon
            $notification.Icon = [System.Drawing.SystemIcons]::Information
            $notification.BalloonTipTitle = "{title}"
            $notification.BalloonTipText = "{message}"
            $notification.Visible = $true
            $notification.ShowBalloonTip(5000)
            '''
            subprocess.run(
                ["powershell", "-Command", ps_script], capture_output=True, check=True
            )
            logger.info("Desktop notification sent via PowerShell")
            return True

        except Exception as e:
            logger.error(f"Windows notification failed: {e}")
            return False

    def _send_linux_notification(self, title: str, message: str) -> bool:
        """Send Linux desktop notification"""
        try:
            # Try plyer first (cross-platform library)
            try:
                from plyer import notification

                notification.notify(
                    title=title, message=message, app_name="Trading System", timeout=10
                )
                logger.info("Desktop notification sent via plyer")
                return True
            except ImportError:
                logger.debug("plyer not available, trying native Linux methods")
            except Exception as e:
                logger.warning(f"plyer notification failed: {e}, trying fallback")

            # Try notify-send (most common on Linux)
            subprocess.run(
                [
                    "notify-send",
                    "--app-name=Trading System",
                    "--urgency=normal",
                    title,
                    message,
                ],
                check=True,
                timeout=5,
            )
            logger.info("Desktop notification sent via notify-send")
            return True

        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            try:
                # Try zenity as fallback
                subprocess.run(
                    ["zenity", "--info", f"--title={title}", f"--text={message}"],
                    check=True,
                    timeout=10,
                )
                logger.info("Desktop notification sent via zenity")
                return True
            except (
                subprocess.CalledProcessError,
                FileNotFoundError,
                subprocess.TimeoutExpired,
            ):
                logger.warning(
                    "No desktop notification system found (install notify-send or zenity)"
                )
                return False

    def send_email_notification(
        self, subject: str, body: str, recipient: str | None = None
    ) -> bool:
        """Send email notification (placeholder for future implementation)"""
        logger.info(f"Email notification: {subject} - {body}")
        # TODO: Implement email sending using smtplib
        return True

    def send_whatsapp_web(self, message: str, phone: str | None = None) -> bool:
        """Send WhatsApp message via web interface (cross-platform)"""
        try:
            # URL-encode the message
            encoded_message = message.replace(" ", "%20").replace("\n", "%0A")

            # Use default phone number if not provided
            if phone is None:
                phone = "+447384545771"  # Default from original WhatsApp.py

            # Create WhatsApp web URL
            whatsapp_url = (
                f"https://web.whatsapp.com/send?phone={phone}&text={encoded_message}"
            )

            # Open in default browser
            if self.is_windows:
                subprocess.run(["start", whatsapp_url], shell=True)
            elif self.is_linux:
                # Try common Linux browsers
                browsers = ["xdg-open", "firefox", "chromium", "google-chrome"]
                for browser in browsers:
                    try:
                        subprocess.run([browser, whatsapp_url], check=True, timeout=5)
                        return True
                    except (
                        subprocess.CalledProcessError,
                        FileNotFoundError,
                        subprocess.TimeoutExpired,
                    ):
                        continue
                logger.warning("No suitable browser found for WhatsApp Web")
                return False

            return True

        except Exception as e:
            logger.error(f"WhatsApp web notification failed: {e}")
            return False

    def send_trading_alert(
        self, alert_type: str, symbol: str, message: str, price: float | None = None
    ) -> bool:
        """Send comprehensive trading alert using multiple channels"""

        # Format the alert message
        title = f"Trading Alert: {alert_type}"
        if price:
            full_message = f"{symbol}: {message} (Price: ${price:.2f})"
        else:
            full_message = f"{symbol}: {message}"

        success = False

        # Send desktop notification
        if self.send_desktop_notification(title, full_message):
            success = True

        # Log the alert
        logger.info(f"Trading Alert - {alert_type}: {full_message}")

        # Optional: Send WhatsApp for critical alerts
        if alert_type.lower() in ["error", "critical", "loss"]:
            self.send_whatsapp_web(f"{title}: {full_message}")

        return success


# Global notification manager instance
_notification_manager = None


def get_notification_manager() -> NotificationManager:
    """Get global notification manager instance"""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager


# Convenience functions for backward compatibility
def send_notification(title: str, message: str) -> bool:
    """Send a desktop notification"""
    return get_notification_manager().send_desktop_notification(title, message)


def send_trading_alert(
    alert_type: str, symbol: str, message: str, price: float | None = None
) -> bool:
    """Send a trading alert"""
    return get_notification_manager().send_trading_alert(
        alert_type, symbol, message, price
    )


def send_whatsapp(message: str, phone: str | None = None) -> bool:
    """Send WhatsApp message via web interface"""
    return get_notification_manager().send_whatsapp_web(message, phone)


# Example usage and testing
if __name__ == "__main__":
    # Test the notification system
    nm = get_notification_manager()

    print(f"Platform: {nm.platform}")
    print("Testing notifications...")

    # Test desktop notification
    if nm.send_desktop_notification("Trading System", "Notification system test"):
        print("✓ Desktop notification sent")
    else:
        print("✗ Desktop notification failed")

    # Test trading alert
    if nm.send_trading_alert("BUY", "AAPL", "Price target reached", 150.25):
        print("✓ Trading alert sent")
    else:
        print("✗ Trading alert failed")

    print("Notification system test complete!")
