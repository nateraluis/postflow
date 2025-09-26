from django.urls import path
from . import views

app_name = 'subscriptions'

urlpatterns = [
    path('', views.pricing, name='pricing'),
    path('checkout/', views.create_checkout_session, name='checkout'),
    path('success/', views.subscription_success, name='success'),
    path('portal/', views.customer_portal, name='customer_portal'),
    path('webhook/', views.stripe_webhook, name='webhook'),
]