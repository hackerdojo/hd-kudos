from google.appengine.api import mail
from google.appengine.ext import deferred

FROM = 'robot@hackerdojo-kudos.appspotmail.com'

def send_kudos_email(kudos, giver, to):
    body = ["You have been praised with %s kudos" % kudos.amount]
    if kudos.reason:
        body.append(" for:\n\n%s\n\n" % kudos.reason)
    else:
        body.append(".\n\n")
    body.append("The Dojo community is better from your efforts.\n\n")
    body.append("http://kudos.hackerdojo.com/kudos/%s" % kudos.key().id())
    mail.send_mail(
        sender="%s <%s>" % (giver.fullname(), FROM),
        to="%s <%s>" % (to.fullname(), to.user.email()),
        reply_to="%s <%s>" % (giver.fullname(), giver.user.email()),
        subject="[Kudos] Thank you from the community",
        body=''.join(body))