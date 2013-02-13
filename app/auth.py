from tornado import auth
from tornado import web
from tornado import httpclient

import random
import string
import urllib
import urlparse
import logging
import json

import db
from helper import *


class ShowAuthPage(myRequestHandler):
    """
    Show Log in page.

    """
    def get(self):

        set_redirect(self)

        self.clear_cookie('session')
        self.render('auth/start.html',
            google = True if self.settings['google_client_key'] and self.settings['google_client_secret'] else False,
            facebook = True if self.settings['facebook_api_key'] and self.settings['facebook_secret'] else False,
            twitter = True if self.settings['twitter_consumer_key'] and self.settings['twitter_consumer_secret'] else False,
            live = True if self.settings['live_client_key'] and self.settings['live_client_secret'] else False,
        )


class Exit(myRequestHandler):
    """
    Log out.

    """
    def get(self):
        redirect_url = ''
        if self.current_user:
            if self.current_user.provider == 'google':
                redirect_url = 'https://www.google.com/accounts/logout'
            elif self.current_user.provider == 'facebook':
                redirect_url = 'https://www.facebook.com/logout.php?access_token=%s&confirm=1&next=%s://%s/auth' % (self.current_user.access_token, self.request.protocol, self.request.host)
            elif self.current_user.provider == 'live':
                redirect_url = 'https://login.live.com/oauth20_logout.srf?client_id=%s&redirect_uri=%s://%s/auth' % (self.settings['live_client_key'], self.request.protocol, self.request.host)

            self.current_user.logout(self)
        logging.debug(redirect_url)
        self.redirect(redirect_url)


class AuthOAuth2(myRequestHandler, auth.OAuth2Mixin):
    """
    Google, Facebook and MSLive authentication.

    """
    @web.asynchronous
    def get(self, provider):
        set_redirect(self)
        self.oauth2_provider = None

        if provider == 'facebook' and 'facebook_api_key' in self.settings and 'facebook_secret' in self.settings:
            # https://developers.facebook.com/apps
            self.oauth2_provider = {
                'provider':     'facebook',
                'key':          self.settings['facebook_api_key'],
                'secret':       self.settings['facebook_secret'],
                'auth_url':     'https://www.facebook.com/dialog/oauth?client_id=%(id)s&redirect_uri=%(redirect)s&scope=%(scope)s&state=%(state)s',
                'token_url':    'https://graph.facebook.com/oauth/access_token',
                'info_url':     'https://graph.facebook.com/me?access_token=%(token)s',
                'scope':        'email',
                'user_id':      '%(id)s',
                'user_email':   '%(email)s',
                'user_name':    '%(name)s',
                'user_picture': 'http://graph.facebook.com/%(id)s/picture?type=large',
            }

        if provider == 'google' and 'google_client_key' in self.settings and 'google_client_secret' in self.settings:
            # https://code.google.com/apis/console
            self.oauth2_provider = {
                'provider':     'google',
                'key':          self.settings['google_client_key'],
                'secret':       self.settings['google_client_secret'],
                'auth_url':     'https://accounts.google.com/o/oauth2/auth?client_id=%(id)s&redirect_uri=%(redirect)s&scope=%(scope)s&state=%(state)s&response_type=code&approval_prompt=auto&access_type=online',
                'token_url':    'https://accounts.google.com/o/oauth2/token',
                'info_url':     'https://www.googleapis.com/oauth2/v2/userinfo?access_token=%(token)s',
                'scope':        'https://www.googleapis.com/auth/userinfo.profile+https://www.googleapis.com/auth/userinfo.email',
                'user_id':      '%(id)s',
                'user_email':   '%(email)s',
                'user_name':    '%(name)s',
                'user_picture': '%(picture)s',
            }
        if provider == 'live' and 'live_client_key' in self.settings and 'live_client_secret' in self.settings:
            # https://manage.dev.live.com/Applications/Index
            self.oauth2_provider = {
                'provider':     'live',
                'key':          self.settings['live_client_key'],
                'secret':       self.settings['live_client_secret'],
                'auth_url':     'https://login.live.com/oauth20_authorize.srf?client_id=%(id)s&redirect_uri=%(redirect)s&scope=%(scope)s&state=%(state)s&response_type=code',
                'token_url':    'https://login.live.com/oauth20_token.srf',
                'info_url':     'https://apis.live.net/v5.0/me?access_token=%(token)s',
                'scope':        'wl.basic+wl.emails',
                'user_id':      '%(id)s',
                'user_email':   '',
                'user_name':    '%(name)s',
                'user_picture': 'https://apis.live.net/v5.0/%(id)s/picture',
            }

        if not self.oauth2_provider:
            return self.finish()

        self._OAUTH_AUTHORIZE_URL = self.oauth2_provider['auth_url']

        url = self.request.protocol + '://' + self.request.host + '/auth/' + provider

        if not self.get_argument('code', None):
            return self.redirect(self.oauth2_provider['auth_url'] % {
                'id':       self.oauth2_provider['key'],
                'redirect': url,
                'scope':    self.oauth2_provider['scope'],
                'state':    ''.join(random.choice(string.ascii_letters + string.digits) for x in range(16)),
            })

        if self.get_argument('error', None):
            logging.error('%s oauth error: %s' % (provider, self.get_argument('error', None)))
            return self.redirect(get_redirect(self))

        httpclient.AsyncHTTPClient().fetch(self.oauth2_provider['token_url'],
            method = 'POST',
            headers = {'Content-Type': 'application/x-www-form-urlencoded'},
            body = urllib.urlencode({
                'client_id':        self.oauth2_provider['key'],
                'client_secret':    self.oauth2_provider['secret'],
                'redirect_uri':     url,
                'code':             self.get_argument('code', None),
                'grant_type':       'authorization_code',
            }),
            callback = self._got_token,
        )

    @web.asynchronous
    def _got_token(self, response):
        access_token = response.body
        try:
            access_token = json.loads(access_token)
            if 'error' in access_token:
                logging.error('%s oauth error: %s' % (provider, access_token['error']))
                return self.redirect(get_redirect(self))
            access_token = access_token['access_token']
        except:
            try:
                access_token = urlparse.parse_qs(access_token)
                if 'error' in access_token:
                    logging.error('%s oauth error: %s' % (provider, access_token['error']))
                    return self.redirect(get_redirect(self))
                access_token = access_token['access_token'][0]
            except:
                logging.error('%s oauth error' % provider)
                return self.redirect(get_redirect(self))

        httpclient.AsyncHTTPClient().fetch(self.oauth2_provider['info_url'] %  {'token': access_token },
            callback = self._got_user
        )

    @web.asynchronous
    def _got_user(self, response):
        try:
            user = json.loads(response.body)
            access_token = response.effective_url.split('access_token=')[1]
            if 'error' in user:
                logging.error('%s oauth error: %s' % (provider, user['error']))
                return self.redirect(get_redirect(self))
        except:
            return

        if self.oauth2_provider['provider'] == 'facebook':
            db.User().login(
                request_handler = self,
                provider        = self.oauth2_provider['provider'],
                provider_id     = user.setdefault('id', None),
                email           = user.setdefault('email', None),
                name            = user.setdefault('name', None),
                picture         = 'http://graph.facebook.com/%s/picture?type=large' % user.setdefault('id', ''),
                access_token    = access_token
            )
        if self.oauth2_provider['provider'] == 'google':
            db.User().login(
                request_handler = self,
                provider        = self.oauth2_provider['provider'],
                provider_id     = user.setdefault('id', None),
                email           = user.setdefault('email', None),
                name            = user.setdefault('name', None),
                picture         = user.setdefault('picture', None),
                access_token    = access_token
            )
        if self.oauth2_provider['provider'] == 'live':
            db.User().login(
                request_handler = self,
                provider        = self.oauth2_provider['provider'],
                provider_id     = user.setdefault('id', None),
                email           = user.setdefault('emails', {}).setdefault('preferred', user.setdefault('emails', {}).setdefault('preferred', user.setdefault('personal', {}).setdefault('account', None))),
                name            = user.setdefault('name', None),
                picture         = 'https://apis.live.net/v5.0/%s/picture' % user.setdefault('id', ''),
                access_token    = access_token
            )

        self.redirect(get_redirect(self))


class AuthMobileID(myRequestHandler, auth.OpenIdMixin):
    """
    Estonian Mobile ID authentication.

    """
    @web.asynchronous
    def get(self):
        set_redirect(self)
        self._OPENID_ENDPOINT = 'https://openid.ee/server/xrds/mid'

        if not self.get_argument('openid.mode', None):
            url = self.request.protocol + '://' + self.request.host + '/auth/mobileid'
            self.authenticate_redirect(callback_uri=url)

        self.get_authenticated_user(self.async_callback(self._got_user))

    def _got_user(self, user):
        if not user:
            raise web.HTTPError(500, 'MobileID auth failed')

        db.User().login(
            request_handler = self,
            provider_id     = self.get_argument('openid.identity', None)
        )
        self.redirect(get_redirect(self))


class AuthIDcard(myRequestHandler, auth.OpenIdMixin):
    """
    Estonian ID card authentication.

    """
    @web.asynchronous
    def get(self):
        set_redirect(self)
        self._OPENID_ENDPOINT = 'https://openid.ee/server/eid'

        if not self.get_argument('openid.mode', None):
            return self.authenticate_redirect()

        self.get_authenticated_user(self.async_callback(self._got_user))

    def _got_user(self, user):
        if not user:
            raise web.HTTPError(500, 'IDcard auth failed')

        db.User().login(
            request_handler = self,
            provider_id     = self.get_argument('openid.identity', None)
        )
        self.redirect(get_redirect(self))


class AuthTwitter(myRequestHandler, auth.TwitterMixin):
    """
    Twitter authentication.

    """
    @web.asynchronous
    def get(self):
        set_redirect(self)
        if not self.get_argument('oauth_token', None):
            return self.authenticate_redirect()
        self.get_authenticated_user(self.async_callback(self._got_user))

    def _got_user(self, user):
        if not user:
            raise web.HTTPError(500, 'Twitter auth failed')

        db.User().login(
            request_handler = self,
            provider        = 'twitter',
            provider_id     = '%s' % user.setdefault('id'),
            email           = None,
            name            = user.setdefault('name'),
            picture         = user.setdefault('profile_image_url')
        )
        self.redirect(get_redirect(self))


def set_redirect(rh):
    """
    Saves requested URL to cookie, then (after authentication) we know where to go.

    """
    if rh.get_argument('next', None, strip=True):
        rh.set_secure_cookie('auth_redirect', rh.get_argument('next', default='/', strip=True), 1)


def get_redirect(rh):
    """
    Returns requested URL (or / if not set) from cookie.

    """
    next = rh.get_secure_cookie('auth_redirect')
    if next:
        return next
    return '/'


handlers = [
    ('/auth', ShowAuthPage),
    ('/exit', Exit),
    ('/auth/mobileid', AuthMobileID),
    ('/auth/idcard', AuthIDcard),
    ('/auth/twitter', AuthTwitter),
    ('/auth/(.*)', AuthOAuth2),
]
