import stripe
import json
import logging
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.urls import reverse
from django.utils import timezone
from .models import StripeCustomer, UserSubscription

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


def convert_stripe_timestamp(timestamp):
    """Convert Stripe Unix timestamp to Django timezone-aware datetime"""
    return timezone.make_aware(datetime.fromtimestamp(timestamp))


def pricing(request):
    """Public pricing page"""
    context = {
        'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
        'monthly_price': '$10.00',
        'yearly_price': '$100.00',
        'yearly_savings': '$20.00'
    }
    return render(request, 'subscriptions/pricing.html', context)


@login_required
def create_checkout_session(request):
    """Create Stripe checkout session"""
    if request.user.is_subscribed:
        messages.info(request, "You already have an active subscription!")
        return redirect('home')

    # Get plan type from request (monthly or yearly)
    plan = request.GET.get('plan', 'monthly')

    try:
        # Get or create Stripe customer
        stripe_customer, created = StripeCustomer.objects.get_or_create(
            user=request.user,
            defaults={'stripe_customer_id': ''}
        )

        if created or not stripe_customer.stripe_customer_id:
            # Create customer in Stripe
            customer = stripe.Customer.create(
                email=request.user.email,
                metadata={'user_id': request.user.id}
            )
            stripe_customer.stripe_customer_id = customer.id
            stripe_customer.save()

        # Set pricing based on plan
        if plan == 'yearly':
            price_id = 'postflow-yearly'  # Use the Stripe price ID for yearly plan
            unit_amount = 10000  # $100.00 in cents
            interval = 'year'
            product_name = 'PostFlow Premium (Yearly)'
        else:
            price_id = 'postflow-monthly'  # Use the Stripe price ID for monthly plan
            unit_amount = 1000  # $10.00 in cents
            interval = 'month'
            product_name = 'PostFlow Premium (Monthly)'

        # Create checkout session with promotion code support
        checkout_session = stripe.checkout.Session.create(
            customer=stripe_customer.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,  # Use the Stripe price ID
                'quantity': 1,
            }],
            mode='subscription',
            allow_promotion_codes=True,  # Enable promotion codes
            success_url=request.build_absolute_uri(reverse('subscriptions:success')),
            cancel_url=request.build_absolute_uri(reverse('subscriptions:pricing')),
            metadata={
                'user_id': request.user.id,
                'plan': plan
            }
        )

        return redirect(checkout_session.url)

    except Exception as e:
        logger.error(f"Error creating checkout session: {e}")
        messages.error(request, "There was an error processing your request. Please try again.")
        return redirect('subscriptions:pricing')


@login_required
def subscription_success(request):
    """Success page after subscription - redirect to dashboard"""
    messages.success(request, "Welcome to PostFlow Premium! Your subscription is now active.")
    return redirect('dashboard')


@login_required
def customer_portal(request):
    """Redirect to Stripe Customer Portal for subscription management"""
    try:
        # Get the user's Stripe customer
        stripe_customer = StripeCustomer.objects.get(user=request.user)

        # Create customer portal session
        portal_session = stripe.billing_portal.Session.create(
            customer=stripe_customer.stripe_customer_id,
            return_url=request.build_absolute_uri(reverse('dashboard'))
        )

        return redirect(portal_session.url)

    except StripeCustomer.DoesNotExist:
        messages.error(request, "No subscription found. Please subscribe first.")
        return redirect('subscriptions:pricing')
    except Exception as e:
        logger.error(f"Error creating customer portal session: {e}")
        messages.error(request, "Unable to access billing portal. Please try again.")
        return redirect('home')


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Handle Stripe webhooks"""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError:
        logger.error("Invalid payload")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        logger.error("Invalid signature")
        return HttpResponse(status=400)

    # Handle the event
    if event['type'] == 'customer.subscription.created':
        handle_subscription_created(event['data']['object'])
    elif event['type'] == 'customer.subscription.updated':
        handle_subscription_updated(event['data']['object'])
    elif event['type'] == 'customer.subscription.deleted':
        handle_subscription_deleted(event['data']['object'])
    elif event['type'] == 'invoice.payment_succeeded':
        handle_payment_succeeded(event['data']['object'])
    elif event['type'] == 'invoice.payment_failed':
        handle_payment_failed(event['data']['object'])

    return HttpResponse(status=200)


def handle_subscription_created(subscription):
    """Handle subscription created webhook"""
    try:
        stripe_customer = StripeCustomer.objects.get(
            stripe_customer_id=subscription['customer']
        )

        # Prepare defaults with required fields
        defaults = {
            'stripe_subscription_id': subscription['id'],
            'stripe_customer': stripe_customer,
            'status': subscription.get('status', 'incomplete'),
        }

        # Add optional datetime fields if they exist
        if 'current_period_start' in subscription:
            defaults['current_period_start'] = convert_stripe_timestamp(subscription['current_period_start'])
        else:
            defaults['current_period_start'] = timezone.now()

        if 'current_period_end' in subscription:
            defaults['current_period_end'] = convert_stripe_timestamp(subscription['current_period_end'])
        else:
            # Default to 1 month from now if not provided
            defaults['current_period_end'] = timezone.now() + timezone.timedelta(days=30)

        UserSubscription.objects.update_or_create(
            user=stripe_customer.user,
            defaults=defaults
        )
        logger.info(f"Created subscription for user {stripe_customer.user.email}")
    except StripeCustomer.DoesNotExist:
        logger.error(f"StripeCustomer not found for customer {subscription['customer']}")
    except Exception as e:
        logger.error(f"Error handling subscription created: {e}")


def handle_subscription_updated(subscription):
    """Handle subscription updated webhook"""
    try:
        user_subscription = UserSubscription.objects.get(
            stripe_subscription_id=subscription['id']
        )

        # Update status if provided
        if 'status' in subscription:
            user_subscription.status = subscription['status']

        # Update datetime fields if they exist
        if 'current_period_start' in subscription:
            user_subscription.current_period_start = convert_stripe_timestamp(subscription['current_period_start'])

        if 'current_period_end' in subscription:
            user_subscription.current_period_end = convert_stripe_timestamp(subscription['current_period_end'])

        user_subscription.save()
        logger.info(f"Updated subscription for user {user_subscription.user.email}")
    except UserSubscription.DoesNotExist:
        logger.error(f"UserSubscription not found for subscription {subscription['id']}")
    except Exception as e:
        logger.error(f"Error handling subscription updated: {e}")


def handle_subscription_deleted(subscription):
    """Handle subscription deleted webhook"""
    try:
        user_subscription = UserSubscription.objects.get(
            stripe_subscription_id=subscription['id']
        )
        user_subscription.status = 'canceled'
        user_subscription.save()
        logger.info(f"Cancelled subscription for user {user_subscription.user.email}")
    except UserSubscription.DoesNotExist:
        logger.error(f"UserSubscription not found for subscription {subscription['id']}")


def handle_payment_succeeded(invoice):
    """Handle successful payment"""
    logger.info(f"Payment succeeded for invoice {invoice['id']}")


def handle_payment_failed(invoice):
    """Handle failed payment"""
    logger.warning(f"Payment failed for invoice {invoice['id']}")
