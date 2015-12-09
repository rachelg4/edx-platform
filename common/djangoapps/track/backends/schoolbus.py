"""
SchoolBus analytics service event tracker backend.
"""
from __future__ import absolute_import

import logging
from urlparse import urljoin
import urllib
import urllib2

from django.contrib.auth.models import User
from requests_oauthlib import OAuth1Session

from student.models import anonymous_id_for_user
from track.backends import BaseBackend


LOG = logging.getLogger(__name__)


class SchoolBusAnalyticsBackend(BaseBackend):
    """
    Transmit events to the SchoolBus analytics service
    """
    def __init__(
            self,
            url=None,
            path=None,
            key=None,
            secret=None,
            course_ids=None,
            events=None,
            **kwargs
    ):
        super(SchoolBusAnalyticsBackend, self).__init__(**kwargs)

        self.url = url
        self.path = path
        self.key = key
        self.secret = secret

        # only courses with id in this set will have their data sent
        self.course_ids = set()
        if course_ids is not None:
            self.course_ids = set(course_ids)

        # Only events in this set will have their data sent.
        self.events = set()
        if events is not None:
            self.events = set(events)

        self.oauth = OAuth1Session(self.key, client_secret=self.secret)

    def send(self, event):
        """
        Forward the event to the SchoolBus analytics server
        Exact API here: https://docs.google.com/document/d/1ZB-qwP0bV7ko_xJdJNX1PYKvTyYd4I8CBltfac4dlfw/edit?pli=1#
        OAuth 1 with nonce and body signing
        """

        if not (self.url and self.secret and self.key):
            return None

        # Only currently passing events from pre-defined list.
        event_type = event.get('event_type')
        if event_type not in self.events:
            return None

        if event.get('event_source') != 'server':
            return None

        context = event.get('context')
        if not context:
            return None

        course_id = context.get('course_id')
        if not course_id or course_id not in self.course_ids:
            return None

        user_id = context.get('user_id')
        if not user_id:
            return None

        event_data = event.get('event')
        if not event_data:
            return None

        problem_id = event_data.get('problem_id')
        if not problem_id:
            return None

        answers = event_data.get('answers')

        success = event_data.get('success')
        if not success:
            return None

        is_correct = success == 'correct'

        # put the most expensive operation (DB access) at the end, to not do it needlessly
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            LOG.warning('Can not find a user with user_id: %s', user_id)
            return None

        payload = {
            'course_id': course_id,
            'resource_id': problem_id,
            'student_id': anonymous_id_for_user(user, None),
            'answers': answers,
            'result': is_correct,
            'event_type': event_type,
        }

        endpoint = urljoin(self.url, self.path)

        data = urllib.urlencode(payload)
        req = urllib2.Request(endpoint, data)
        try:
            response = urllib2.urlopen(req)
            data = response.read()

            print "++++++++++++++++++++++"
            print data

            message = response.code
            if message == 200:
                return 'OK'
            else:
                LOG.warning('SchoolBus analytics service returns error status: %s.', message)
                return 'Error'

        except urllib2.HTTPError, error:
            LOG.warning(
                "Unable to send event to SchoolBus analytics service: %s: %s: %s",
                endpoint,
                payload,
                error,
            )
            return None

        except urllib2.URLError, error:
            LOG.warning(
                "Unable to send event to SchoolBus analytics service: %s: %s: %s",
                endpoint,
                payload,
                error,
            )
            return None
