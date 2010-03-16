from google.appengine.ext import webapp, db
from google.appengine.ext.webapp import util, template
from google.appengine.api import urlfetch, memcache, users
from django.utils import simplejson

MONTHLY_POINTS = 10

class Profile(db.Model):
    user = db.UserProperty(auto_current_user_add=True)
    points = db.IntegerProperty(default=MONTHLY_POINTS)
    total_kudos = db.IntegerProperty(default=0)
    monthly_kudos = db.IntegerProperty(default=0)

    @classmethod
    def get_by_user(cls, user):
        profile = cls.all().filter('user =', user).get()
        if not profile:
            profile = cls(user=user)
            profile.put()
        return profile
    
class Kudos(db.Model):
    user_from = db.UserProperty(auto_current_user_add=True)
    user_to = db.UserProperty(required=True)
    amount = db.IntegerProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    

class MainHandler(webapp.RequestHandler):
    @util.login_required
    def get(self):
        user = users.get_current_user()
        profile = Profile.get_by_user(user)
        if user:
            logout_url = users.create_logout_url('/')
        else:
            login_url = users.create_login_url('/')
        usernames = memcache.get('usernames')
        if not usernames:
            usernames = simplejson.loads(urlfetch.fetch('http://localhost/~jeff/users.json').content)
            memcache.set('usernames', usernames, 3600)
        point_options = [n + 1 for n in range(profile.points)]
        self.response.out.write(template.render('templates/main.html', locals()))

    def post(self):
        user = users.get_current_user()
        if not user:
            return
        from_profile = Profile.get_by_user(user)
        points = int(self.request.get('points'))
        if points > from_profile.points:
            points = from_profile.points
        if points < 0:
            points = 0
        # If profile doesn't exist it will be created, no matter if user exists (which is fine)
        to_profile = Profile.get_by_user(users.User(self.request.get('user_to') + '@hackerdojo.com'))
        to_profile.total_kudos += points
        to_profile.monthly_kudos += points
        to_profile.put()
        kudos = Kudos(
            user_to=to_profile.user,
            amount =points
            )
        kudos.put()
        from_profile.points -= points
        from_profile.put()
        self.redirect('/')

def main():
    application = webapp.WSGIApplication([
        ('/', MainHandler)], debug=True)
    util.run_wsgi_app(application)

if __name__ == '__main__':
    main()
