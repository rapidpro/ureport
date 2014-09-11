from email.mime.image import MIMEImage
from django.core.mail import EmailMultiAlternatives
from django.template import loader, Context
from django.conf import settings

def send_dash_email(to_email, subject, template, context):
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'website@textit.in')

    html_template = loader.get_template(template + ".html")
    text_template = loader.get_template(template + ".txt")

    context['subject'] = subject

    html = html_template.render(Context(context))
    text = text_template.render(Context(context))

    message = EmailMultiAlternatives(subject, text, from_email, [to_email])
    message.attach_alternative(html, "text/html")
    message.send()
