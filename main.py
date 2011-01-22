from google.appengine.ext import webapp, db
from google.appengine.ext.webapp import util, template
from google.appengine.api import urlfetch, memcache, users
from google.appengine.api.labs import taskqueue
from django.utils import simplejson
import datetime

from shared.api import damain

MONTHLY_POINTS = 10


def fullname(username):
    fullname = memcache.get('/users/%s:fullname' % username)
    if not fullname:
        taskqueue.add(url='/worker/user', params={'username': username})
        memcache.set('/users/%s:fullname' % username, username, 10)
        return username
    else:
        return fullname

class UserWorker(webapp.RequestHandler):
    def post(self):
        username = self.request.get('username')
        month_ttl = 3600*24*28
        user = domain('/users/%s' % username, month_ttl)
        memcache.set('/users/%s:fullname' % username, "%s %s" % (user['first_name'], user['last_name']), month_ttl)

def username(user):
    return user.nickname().split('@')[0] if user else None

class Profile(db.Model):
    user    = db.UserProperty(auto_current_user_add=True)
    to_give = db.IntegerProperty(default=MONTHLY_POINTS)
    received_total      = db.IntegerProperty(default=0)
    received_this_month = db.IntegerProperty(default=0)
    gave_total          = db.IntegerProperty(default=0)
    gave_this_month     = db.IntegerProperty(default=0)

    def fullname(self):
        return fullname(username(self.user))

    @classmethod
    def get_by_user(cls, user):
        profile = cls.all().filter('user =', user).get()
        if not profile and user:
            profile = cls(user=user)
            profile.put()
        return profile
    
    @classmethod
    def top_receivers_this_month(cls, refresh=False):
        receivers = memcache.get('top_receivers_this_month')
        if not receivers or refresh:
            receivers = cls.all().filter('received_this_month >', 0).order('-received_this_month')
            memcache.set('top_receivers_this_month', receivers, 300)
        return receivers
    
    @classmethod
    def top_givers_this_month(cls, refresh=False):
        givers = memcache.get('top_givers_this_month')
        if not givers or refresh:
            givers = cls.all().filter('gave_this_month >', 0).order('-gave_this_month')
            memcache.set('top_givers_this_month', givers, 300)
        return givers
            
    
class Kudos(db.Model):
    user_from = db.UserProperty(auto_current_user_add=True)
    user_to = db.UserProperty(required=True)
    amount = db.IntegerProperty(required=True)
    reason = db.StringProperty()
    created = db.DateTimeProperty(auto_now_add=True)
    
    def from_profile(self):
        return Profile.all().filter('user =', self.user_from).get()
        
    def to_profile(self):
        return Profile.all().filter('user =', self.user_to).get()
    
    def hearts(self):
        return "&hearts;" * self.amount
    
class MainHandler(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()
        profile = Profile.get_by_user(user)
        if user:
            if not memcache.get('monthly:%s' % profile.key().id()):
                profile.to_give = MONTHLY_POINTS
                profile.gave_this_month = 0
                profile.received_this_month = 0
                profile.put()
                memcache.set('monthly:%s' % profile.key().id(), True, 3600*24*30)
            
            logout_url = users.create_logout_url('/')
            points_remaining = "&hearts;"*profile.to_give
            points_used = "&hearts;"*(MONTHLY_POINTS-profile.to_give)
            point_options = [(n + 1,"&hearts;"*(n+1)) for n in range(profile.to_give)]
        else:
            login_url = users.create_login_url('/')
            points_remaining = 0
            points_used = 0
            point_options = None
            
        names = []
        usernames = {}
        for u in domain('/users'):
            name = fullname(u)
            if not u == username(user):
                usernames[name] = u
                names.append(name)
        usernames = simplejson.dumps(usernames)
        names = simplejson.dumps(names)
        
        # monthly leader board
        receive_leaders = Profile.top_receivers_this_month()
        give_leaders = Profile.top_givers_this_month()
        self.response.out.write(template.render('templates/main.html', locals()))

    def post(self):
        user = users.get_current_user()
        if not user or not self.request.get('user_to') in domain('/users'):
            self.redirect('/')
            return
        from_profile = Profile.get_by_user(user)
        kudos_to_give = int(self.request.get('points'))
        if kudos_to_give > from_profile.to_give:
            kudos_to_give = from_profile.to_give
        if kudos_to_give < 0:
            kudos_to_give = 0
        # If profile doesn't exist it will be created, no matter if user exists (which is fine)
        to_profile = Profile.get_by_user(users.User(self.request.get('user_to') + '@hackerdojo.com'))
        to_profile.received_total += kudos_to_give
        to_profile.received_this_month += kudos_to_give
        to_profile.put()
        kudos = Kudos(
            user_to=to_profile.user,
            amount =kudos_to_give,
            reason =self.request.get('reason'),
            )
        kudos.put()
        # if you try to give yourself kudos, you lose the points, as this put overwrites to_profile.put
        from_profile.to_give -= kudos_to_give
        from_profile.gave_this_month += kudos_to_give
        from_profile.gave_total += kudos_to_give
        from_profile.put()
        self.redirect('/kudos/%s' % kudos.key().id())

class CertificateHandler(webapp.RequestHandler):
    def get(self, kudos_id):
        kudos = Kudos.get_by_id(int(kudos_id))
        if kudos:
            self.response.out.write(template.render('templates/certificate.html', locals()))
        else:
            self.redirect('/')

class CronHandler(webapp.RequestHandler):  
    def get(self):
        self.post()
    
    def post(self):
        for profile in Profile.all():
            if not memcache.get('monthly:%s' % profile.key().id()):
                profile.to_give = MONTHLY_POINTS
                profile.gave_this_month = 0
                profile.received_this_month = 0
                profile.put()
                memcache.set('monthly:%s' % profile.key().id(), True, 3600*24*30)
        self.response.out.write("Finished.")

def main():
    application = webapp.WSGIApplication([
        ('/', MainHandler), 
        ('/kudos/(\d+)', CertificateHandler),
        ('/reset_points', CronHandler),
        ('/worker/user', UserWorker), ], debug=True)
    util.run_wsgi_app(application)

if __name__ == '__main__':
    main()
