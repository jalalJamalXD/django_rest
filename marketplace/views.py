from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from .context_processors import get_cart_amounts, get_cart_counter
from django.db.models import Prefetch

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from datetime import date, datetime

from accounts.models import UserProfile
from orders.forms import OrderForm
from vendor.models import OpeningHour, Vendor
from menu.models import Category, FoodItem
from .models import Cart


# Create your views here.


def marketplace(request):
    vendors = Vendor.objects.filter(is_approved=True, user__is_active=True)
    vendor_count = vendors.count()

    # opening_hours = OpeningHour.objects.filter(vendor=vendors).order_by('day', '-from_hour')
    # today_date = date.today()
    # today = today_date.isoweekday()

    # current_opening_hours = OpeningHour.objects.filter(
    #     vendor=vendors, day=today)

    context = {'vendors': vendors, 'vendor_count': vendor_count}
    return render(request, 'marketplace/listings.html', context)


def vendor_detail(request, vendor_slug):
    vendor = get_object_or_404(Vendor, vendor_slug=vendor_slug)

    categories = Category.objects.filter(vendor=vendor).prefetch_related(
        Prefetch(
            'fooditems',
            queryset=FoodItem.objects.filter(is_available=True),
        )
    )

    opening_hours = OpeningHour.objects.filter(
        vendor=vendor).order_by('day', '-from_hour')

    # Check current day's opening hours.
    today_date = date.today()
    today = today_date.isoweekday()

    current_opening_hours = OpeningHour.objects.filter(
        vendor=vendor, day=today)

    if request.user.is_authenticated:
        cart_items = Cart.objects.filter(user=request.user)
    else:
        cart_items = None

    context = {'vendor': vendor, 'categories': categories,
               'cart_items': cart_items, 'opening_hours': opening_hours, 'current_opening_hours': current_opening_hours}
    return render(request, 'marketplace/vendor_detail.html', context)


def add_to_cart(request, food_id):
    if request.user.is_authenticated:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            # Check if the food item exists
            try:
                fooditem = FoodItem.objects.get(id=food_id)
                # Check if the user has already added the food to the cart
                try:
                    chkCart = Cart.objects.get(
                        user=request.user, fooditem=fooditem)
                    # increase the cart quantity
                    chkCart.quantity += 1
                    chkCart.save()
                    return JsonResponse({'status': 'Success', 'message': 'Increased the card!', 'cart_counter': get_cart_counter(request), 'qty': chkCart.quantity, 'cart_amount': get_cart_amounts(request)})

                except:
                    chkCart = Cart.objects.create(
                        user=request.user, fooditem=fooditem, quantity=1)
                    return JsonResponse({'status': 'Success', 'message': 'Added The Food Card', 'cart_counter': get_cart_counter(request), 'qty': chkCart.quantity, 'cart_amount': get_cart_amounts(request)})
            except:
                return JsonResponse({'status': 'Failed', 'message': 'This Food does not exist!'})
        else:
            return JsonResponse({'status': 'Failed', 'message': 'invalid request!'})
    else:
        return JsonResponse({'status': 'login_required', 'message': 'Please login first!'})


def decrease_cart(request, food_id):
    if request.user.is_authenticated:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            # Check if the food item exists
            try:
                fooditem = FoodItem.objects.get(id=food_id)
                # Check if the user has already added the food to the cart
                try:
                    chkCart = Cart.objects.get(
                        user=request.user, fooditem=fooditem)
                    # deacrease the cart quantity
                    if chkCart.quantity > 1:
                        chkCart.quantity -= 1
                        chkCart.save()
                    else:
                        chkCart.delete()
                        chkCart.quantity = 0

                    return JsonResponse({'status': 'Success', 'cart_counter': get_cart_counter(request), 'qty': chkCart.quantity, 'cart_amount': get_cart_amounts(request)})

                except:
                    return JsonResponse({'status': 'Failed', 'message': 'you do not have the item in your Cart'})
            except:
                return JsonResponse({'status': 'Failed', 'message': 'This Food does not exist!'})
        else:
            return JsonResponse({'status': 'Failed', 'message': 'invalid request!'})
    else:
        return JsonResponse({'status': 'login_required', 'message': 'Please login first!'})


@login_required(login_url='login')
def cart(request):
    cart_items = Cart.objects.filter(user=request.user).order_by('created_at')

    context = {'cart_items': cart_items}
    return render(request, 'marketplace/cart.html', context)


def delete_cart(request, cart_id):
    if request.user.is_authenticated:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            try:
                # check if the cart item exists
                cart_item = Cart.objects.get(user=request.user, id=cart_id)
                if cart_id:
                    cart_item.delete()
                    return JsonResponse({'status': 'Success', 'message': 'Cart item has been deleted!!', 'cart_counter': get_cart_counter(request), 'cart_amount': get_cart_amounts(request)})

            except:
                return JsonResponse({'status': 'Failed', 'message': 'This Cart Item does not exist!'})

        else:
            return JsonResponse({'status': 'Failed', 'message': 'invalid request!'})


def search(request):
    if not 'address' in request.GET:
        return redirect('marketplace')

    else:
        address = request.GET['address']
        latitude = request.GET['lat']
        longitude = request.GET['lng']
        radius = request.GET['radius']
        keyword = request.GET['keyword']

        # get vendor ids that has the food item
        fetch_vendors_by_fooditem = FoodItem.objects.filter(
            food_title__icontains=keyword, is_available=True, ).values_list('vendor', flat=True)

        vendors = Vendor.objects.filter(Q(id__in=fetch_vendors_by_fooditem) | Q(
            vendor_name__icontains=keyword, is_approved=True, user__is_active=True))
        if latitude and longitude and radius:
            pnt = GEOSGeometry('POINT(%s %s)' % (longitude, latitude))

            vendors = Vendor.objects.filter(Q(id__in=fetch_vendors_by_fooditem) | Q(
                vendor_name__icontains=keyword, is_approved=True, user__is_active=True),
                user_profile__location__distance_lte=(pnt, D(km=radius))
            ).annotate(distance=Distance("user_profile__location", pnt)).order_by("distance")

            for v in vendors:
                v.kms = round(v.distance.km, 1)

        vendor_count = vendors.count()
        context = {'vendors': vendors, 'vendor_count': vendor_count,
                   'source_location': address}

        return render(request, 'marketplace/listings.html', context)


@login_required(login_url='login')
def checkout(request):
    cart_items = Cart.objects.filter(user=request.user).order_by('created_at')
    cart_count = cart_items.count()

    if cart_count <= 0:
        return redirect('marketplace')

    user_profile = UserProfile.objects.get(user=request.user)
    default_values = {
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
        'phone': request.user.phone_number,
        'email': request.user.email,
        'address': user_profile.address,
        'country': user_profile.country,
        'state': user_profile.state,
        'city': user_profile.city,
        'pin_code': user_profile.pin_code,



    }
    form = OrderForm(initial=default_values)

    context = {'form': form, 'cart_items': cart_items, }
    return render(request, 'marketplace/checkout.html', context)
