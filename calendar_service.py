import datetime
import os.path
from datetime import timezone, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class CalendarService:
    def __init__(self, credentials_path="credentials.json", SCOPES=["https://www.googleapis.com/auth/calendar"], timezone='UTC'):
        self.credentials_path = credentials_path
        self.SCOPES = SCOPES
        self.timezone = timezone
        self.service = self.get_service()

    def get_service(self):
        creds = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", self.SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, self.SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open("token.json", "w") as token:
                token.write(creds.to_json())

        try:
            service = build("calendar", "v3", credentials=creds)
            return service
        except HttpError as error:
            print(f"An error occurred: {error}")
            return None

    def get_events(self, timeMin=None, calendarID="primary", timeMax=None, maxResults=20):
        now = datetime.datetime.now(timezone.utc).isoformat()

        if timeMin is None:
            timeMin = (datetime.datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        if timeMax is None:
            timeMax = now

        if self.service is None:
            self.service = self.get_service()

        events_result = self.service.events().list(
            calendarId=calendarID,
            timeMin=timeMin,
            timeMax=timeMax,
            maxResults=maxResults,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        return events_result.get("items", [])

    def create_event(self, summary, start_time, duration_minutes=30, description="", attendees=None):
        if self.service is None:
            self.service = self.get_service()

        start = datetime.datetime.fromisoformat(start_time).astimezone(timezone.utc)
        end = start + timedelta(minutes=duration_minutes)

        event = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start.isoformat(), 'timeZone': self.timezone},
            'end': {'dateTime': end.isoformat(), 'timeZone': self.timezone},
            'attendees': [{'email': attendee} for attendee in attendees] if attendees else []
        }

        created_event = self.service.events().insert(
            calendarId='primary',
            body=event,
            sendUpdates='all'
        ).execute()

        print('Event created:', created_event.get('htmlLink'))
        return created_event

    def get_free_availability(self, timeMin, timeMax, calendarID="primary"):
        if self.service is None:
            self.service = self.get_service()

        body = {
            "timeMin": timeMin,
            "timeMax": timeMax,
            "timeZone": self.timezone,
            "items": [{"id": calendarID}],
        }

        freebusy_result = self.service.freebusy().query(body=body).execute()
        busy_times = freebusy_result["calendars"][calendarID]["busy"]

        availability = []
        last_end = datetime.datetime.fromisoformat(timeMin).astimezone(timezone.utc)

        for busy in busy_times:
            busy_start = datetime.datetime.fromisoformat(busy["start"].replace('Z', '+00:00')).astimezone(timezone.utc)
            busy_end = datetime.datetime.fromisoformat(busy["end"].replace('Z', '+00:00')).astimezone(timezone.utc)

            if last_end < busy_start:
                availability.append(
                    {"start": last_end.isoformat(), "end": busy_start.isoformat()}
                )

            last_end = max(last_end, busy_end)

        if last_end < datetime.datetime.fromisoformat(timeMax).astimezone(timezone.utc):
            availability.append(
                {"start": last_end.isoformat(), "end": timeMax}
            )

        return availability

    def get_event_summaries(self, events):
        ''' Returns only the event's name, starttime and endtime'''
        summaries = []
        for event in events:
            summary = event.get("summary", "No Title")
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            summaries.append({"summary": summary, "start": start, "end": end})
        return summaries


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