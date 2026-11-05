"""WebSocket consumer for trip live-location updates."""

import asyncio
from asgiref.sync import sync_to_async

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model
from django.utils import timezone

from trips.models import ActiveTrip
from trips.services import record_ping

User = get_user_model()


class TripLocationConsumer(AsyncJsonWebsocketConsumer):
    """Handle WebSocket connections for trip location tracking.

    Authorization mirrors the HTTP views:
    - Conductors and matatu owners may publish location updates.
    - Passengers with an active journey, conductors, owners, and admins may subscribe.
    """

    async def connect(self):
        self.trip_id = self.scope['url_route']['kwargs']['trip_id']
        self.trip = None
        self.user = self.scope['user']
        self.group_name = None

        # Anonymous users cannot connect
        if not self.user.is_authenticated:
            await self.close()
            return

        # Fetch trip
        try:
            self.trip = await sync_to_async(ActiveTrip.objects.get)(
                pk=self.trip_id, status=ActiveTrip.Status.ACTIVE
            )
        except ActiveTrip.DoesNotExist:
            await self.close()
            return

        # Check subscribe authorization
        if not await self._can_subscribe(self.user, self.trip):
            await self.close()
            return

        self.group_name = f'trip_{self.trip_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send initial connected event
        await self.send_json({
            'type': 'connected',
            'trip_id': self.trip_id,
        })

    async def disconnect(self, close_code):
        if getattr(self, 'group_name', None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content):
        msg_type = content.get('type')

        if msg_type == 'location.update':
            await self._handle_location_update(content)
        else:
            await self.send_json({
                'type': 'error',
                'reason': f'Unknown message type: {msg_type}',
            })

    async def _handle_location_update(self, content):
        """Process a location.update message from a conductor/owner."""

        # Check publish authorization
        if not await self._can_publish(self.user, self.trip):
            await self.send_json({
                'type': 'location.rejected',
                'trip_id': self.trip_id,
                'reason': 'Not authorized to publish locations for this trip',
            })
            return

        # Extract fields
        try:
            latitude = content['latitude']
            longitude = content['longitude']
        except (KeyError, TypeError):
            await self.send_json({
                'type': 'location.rejected',
                'trip_id': self.trip_id,
                'reason': 'latitude and longitude are required',
            })
            return

        recorded_at = content.get('recorded_at')
        accuracy_m = content.get('accuracy_m')

        # Call the shared service via sync-to-async bridge
        try:
            result = await sync_to_async(record_ping, thread_sensitive=True)(
                trip=self.trip,
                latitude=latitude,
                longitude=longitude,
                recorded_at=recorded_at,
            )
        except ValueError as exc:
            await self.send_json({
                'type': 'location.rejected',
                'trip_id': self.trip_id,
                'reason': str(exc),
            })
            return

        # Refresh trip data for stale calculation
        await sync_to_async(self.trip.refresh_from_db)()

        # Build the accepted payload
        gps_age = self.trip.gps_age_seconds
        payload = {
            'type': 'location.accepted',
            'trip_id': self.trip_id,
            'latitude': float(self.trip.current_latitude),
            'longitude': float(self.trip.current_longitude),
            'timestamp': self.trip.last_ping_at.isoformat() if self.trip.last_ping_at else None,
            'gps_age_seconds': gps_age,
            'is_stale': self.trip.is_stale,
        }
        if accuracy_m is not None:
            payload['accuracy_m'] = accuracy_m

        # Broadcast to the trip group
        await self.channel_layer.group_send(
            self.group_name,
            payload,
        )

    # -- Group message handlers ------------------------------------------------

    async def location_accepted(self, event):
        """Forward broadcasted location.accepted to connected clients."""
        await self.send_json(event)

    async def trip_completed(self, event):
        """Forward broadcasted trip.completed to connected clients."""
        await self.send_json(event)

    # -- Authorization helpers --------------------------------------------------

    @staticmethod
    @sync_to_async
    def _can_publish(user, trip):
        """Mirror ping() authorization: conductor or matatu owner."""
        user_matatu = getattr(user, 'matatu', None)
        return (
            user_matatu == trip.matatu
            or trip.matatu.owner == user
            or trip.matatu.conductor.filter(pk=user.pk).exists()
        )

    @staticmethod
    @sync_to_async
    def _can_subscribe(user, trip):
        """Allow conductor, owner, admin, or passengers with an active journey."""
        from journeys.models import JourneySession

        # Admins can subscribe to any trip
        if user.role == User.ADMIN:
            return True

        # Conductor / owner
        user_matatu = getattr(user, 'matatu', None)
        if (
            user_matatu == trip.matatu
            or trip.matatu.owner == user
            or trip.matatu.conductor.filter(pk=user.pk).exists()
        ):
            return True

        # Passenger with an active journey session for this trip
        active_statuses = [
            JourneySession.Status.DESTINATION_SELECTED,
            JourneySession.Status.IN_TRANSIT,
            JourneySession.Status.APPROACHING,
        ]
        return JourneySession.objects.filter(
            passenger=user, trip=trip, status__in=active_statuses
        ).exists()
