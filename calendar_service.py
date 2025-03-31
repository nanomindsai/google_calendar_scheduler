import os
import datetime
from datetime import timezone, timedelta
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from loguru import logger
import pytz

class CalendarService:
    def __init__(self, credentials_path="credentials.json", SCOPES=["https://www.googleapis.com/auth/calendar"], timezone_str='UTC'):
        self.credentials_path = credentials_path
        self.SCOPES = SCOPES
        self.timezone_str = timezone_str
        self.timezone = pytz.timezone(timezone_str)
        self.service = self.get_service()

    def get_service(self):
        creds = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", self.SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, self.SCOPES)
                creds = flow.run_local_server(port=0)
            with open("token.json", "w") as token:
                token.write(creds.to_json())

        try:
            return build("calendar", "v3", credentials=creds)
        except HttpError as error:
            logger.error(f"Failed to build calendar service: {error}")
            return None
        
    def set_timezone(self, timezone_str):
        """
        Set the timezone attribute dynamically.
        
        :param timezone_str: New timezone string (e.g., 'Australia/Sydney')
        """
        try:
            self.timezone = pytz.timezone(timezone_str)
            self.timezone_str = timezone_str  # ✅ store string for serialization
            logger.info(f"Timezone updated to {self.timezone}")
        except Exception as e:
            logger.warning(f"Failed to set timezone '{timezone_str}': {e}")
            self.timezone = pytz.utc
            self.timezone_str = "UTC"

    def get_current_datetime(self):
        """
        Returns the current datetime as an ISO 8601 string based on the instance's timezone.
        """
        try:
            now = datetime.datetime.now(self.timezone).isoformat()
            return now
        except Exception as e:
            logger.warning(f"Could not parse timezone '{self.timezone}': {e}. Defaulting to UTC.")
            return datetime.datetime.now(timezone.utc)


    def get_events(self, time_min=None, time_max=None, max_results=20, calendar_id="primary"):
        if not self.service:
            self.service = self.get_service()

        now = datetime.datetime.now(self.timezone)
        if time_min is None:
            time_min = (now - timedelta(days=7)).isoformat()
        if time_max is None:
            time_max = now.isoformat()

        events_result = self.service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])

        event_strings = [f"Event '{event['summary']}' from {event['start']['dateTime']} to {event['end']['dateTime']}" for event in events]

        return "\n".join(event_strings)

    def create_event(self, summary, start_time, duration_minutes=30, description="", attendees=None):
        if not self.service:
            self.service = self.get_service()

        # Convert naive input to localized datetime
        try:
            start_naive = datetime.datetime.fromisoformat(start_time)
            start_local = self.timezone.localize(start_naive)
        except ValueError as e:
            logger.error(f"Invalid start_time format: {e}")
            return None

        end_local = start_local + timedelta(minutes=duration_minutes)

        event_body = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_local.isoformat(),
                'timeZone': self.timezone_str  # must be a string
            },
            'end': {
                'dateTime': end_local.isoformat(),
                'timeZone': self.timezone_str
            },
            'attendees': [{'email': email} for email in attendees] if attendees else []
        }

        try:
            created_event = self.service.events().insert(
                calendarId='primary',
                body=event_body,
                sendUpdates='all'
            ).execute()

            event_str = f"Created event '{created_event['summary']}' at {created_event['start']['dateTime']} lasting {duration_minutes} minutes. Link: {created_event.get('htmlLink')}"
            logger.info(event_str)
            return event_str
        except Exception as e:
            logger.error(f"Failed to create event: {e}")
            return None


    def get_free_availability(self, time_min, time_max, calendar_id="primary"):
        if not self.service:
            self.service = self.get_service()

        # Parse input and localize to instance timezone
        try:
            dt_min = self.timezone.localize(datetime.datetime.fromisoformat(time_min))
            dt_max = self.timezone.localize(datetime.datetime.fromisoformat(time_max))
        except ValueError as e:
            logger.error(f"Invalid datetime format: {e}")
            return []

        # Convert to UTC ISO 8601 with Z
        time_min_utc = dt_min.astimezone(pytz.utc).isoformat().replace("+00:00", "Z")
        time_max_utc = dt_max.astimezone(pytz.utc).isoformat().replace("+00:00", "Z")

        logger.debug(f"Querying between {time_min_utc} and {time_max_utc} (converted from local timezone)")

        body = {
            "timeMin": time_min_utc,
            "timeMax": time_max_utc,
            "timeZone": self.timezone_str,
            "items": [{"id": calendar_id}]
        }

        freebusy_result = self.service.freebusy().query(body=body).execute()
        busy_times = freebusy_result["calendars"][calendar_id]["busy"]

        availability = []
        last_end = dt_min

        for busy in busy_times:
            busy_start = datetime.datetime.fromisoformat(busy["start"].replace("Z", "+00:00"))
            busy_end = datetime.datetime.fromisoformat(busy["end"].replace("Z", "+00:00"))

            if last_end < busy_start:
                availability.append(f"Free from {last_end.isoformat()} to {busy_start.isoformat()}")

            last_end = max(last_end, busy_end)

        if last_end < dt_max:
            availability.append(f"Free from {last_end.isoformat()} to {dt_max.isoformat()}")

        return "\n".join(availability)




### Example usage
def main():
    service = CalendarService()

    print("Fetching events from the past week:")
    events = service.get_events()
    event_summaries = service.get_event_summaries(events)
    for event in event_summaries:
        print(f"Summary: {event['summary']}")
        print(f"Start: {event['start']}")
        print(f"End: {event['end']}\n")

    print("\nCreating an event:")
    event = service.create_event(
        summary="Test Meeting",
        start_time=(datetime.datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        duration_minutes=60,
        description="Testing event creation",
        attendees=["example@example.com"]
    )

    print("\nChecking availability for tomorrow:")
    availability = service.get_free_availability(
        timeMin=(datetime.datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=9, minute=0, second=0).isoformat(),
        timeMax=(datetime.datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=17, minute=0, second=0).isoformat()
    )
    for slot in availability:
        print(slot)

if __name__ == "__main__":
    main()