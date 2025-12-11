import datetime
import app.logic as logic

class SchedulerService:
    """Handles the business logic for server restart scheduling."""

    def __init__(self, server_name):
        """
        Initializes the service for a specific server.
        Args:
            server_name (str): The name of the server to manage.
        """
        self.server_name = server_name
        self.scheduler = logic.Scheduler(server_name)
        self.schedule = self.scheduler.get_schedule()

    def get_status(self):
        """
        Calculates the current scheduling status, including time remaining and due status.
        
        Returns:
            dict: A dictionary containing 'is_due' (bool) and 'remaining_seconds' (int/None).
                  Returns None if no schedule is active.
        """
        if not self.schedule:
            return None

        now = datetime.datetime.now()
        remaining_seconds = None

        if self.schedule["type"] == "interval":
            last_run_str = self.schedule.get("last_run")
            if last_run_str:
                last_run = datetime.datetime.fromisoformat(last_run_str)
                interval = datetime.timedelta(hours=self.schedule["interval_hours"])
                next_restart = last_run + interval
                remaining_seconds = (next_restart - now).total_seconds()
        
        elif self.schedule["type"] == "time":
            restart_time_str = self.schedule["restart_time"]
            hour, minute = map(int, restart_time_str.split(":"))
            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            remaining_seconds = (target_time - now).total_seconds()

        return {
            "is_due": self.scheduler.check_due(),
            "remaining_seconds": remaining_seconds
        }

    def get_warning_message(self, remaining_seconds, sent_warnings):
        """
        Determines if a warning message should be sent based on the time remaining.

        Args:
            remaining_seconds (int): Time until restart in seconds.
            sent_warnings (set): A set of already sent warning keys (e.g., {'1h', '30m'}).

        Returns:
            tuple: A tuple containing the warning key and the message string (e.g., ('1h', 'Server will restart...')),
                   or (None, None) if no warning is needed.
        """
        if remaining_seconds is None or remaining_seconds <= 0:
            return None, None

        # Widened time windows to 30s to ensure they are not missed by the 30s polling loop.
        if 3600 < remaining_seconds <= 3630 and '1h' not in sent_warnings:
            return '1h', "Server will restart in 1 hour!"
        elif 1800 < remaining_seconds <= 1830 and '30m' not in sent_warnings:
            return '30m', "Server will restart in 30 minutes!"
        elif 900 < remaining_seconds <= 930 and '15m' not in sent_warnings:
            return '15m', "Server will restart in 15 minutes!"
        elif 60 < remaining_seconds <= 90 and '1m' not in sent_warnings:
            return '1m', "Server will restart in 1 minute!"
        
        return None, None
