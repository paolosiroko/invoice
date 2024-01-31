from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from .forms import *
from .models import *
from .functions import *

from django.contrib.auth.models import User, auth
from random import randint
from uuid import uuid4

from django.http import HttpResponse

import pdfkit
from django.template.loader import get_template
import os


#Anonymous required
def anonymous_required(function=None, redirect_url=None):

   if not redirect_url:
       redirect_url = 'dashboard'

   actual_decorator = user_passes_test(
       lambda u: u.is_anonymous,
       login_url=redirect_url
   )

   if function:
       return actual_decorator(function)
   return actual_decorator


def index(request):
    context = {}
    return render(request, 'invoice/index.html', context)


@anonymous_required
def login(request):
    context = {}
    if request.method == 'GET':
        form = UserLoginForm()
        context['form'] = form
        return render(request, 'invoice/login.html', context)

    if request.method == 'POST':
        form = UserLoginForm(request.POST)

        username = request.POST['username']
        password = request.POST['password']

        user = auth.authenticate(username=username, password=password)
        if user is not None:
            auth.login(request, user)

            return redirect('dashboard')
        else:
            context['form'] = form
            messages.error(request, 'Invalid Credentials')
            return redirect('login')


    return render(request, 'invoice/login.html', context)


@login_required
def dashboard(request):
    clients = Client.objects.all().count()
    invoices = Invoice.objects.all().count()
    paidInvoices = Invoice.objects.filter(status='PAID').count()
    labels = []
    data = []

    if request.user.is_staff:
        stockqueryset = Product.objects.all()
        for item in stockqueryset:
            labels.append(item.quantity)
            data.append(item.total)
           
    else:
        stockqueryset = Invoice.objects.filter(client=request.user.client)
        bills = Invoice.objects.filter(client=request.user.client).count()
        for item in stockqueryset:
            labels.append(item.status)
            data.append(bills)


    context = {
        'labels': labels,
        'data': data,
        'clients': clients,
        'invoices': invoices
     }
    
    return render(request, 'invoice/dashboard.html', context)




@login_required
def invoices(request):
    if request.user.is_staff:
        # Admin can see all invoices
        invoices = Invoice.objects.all()
    else:
        # Non-admin user (client) can only see their related invoices
        invoices = Invoice.objects.filter(client=request.user.client)
        
    return render(request, 'invoice/invoices.html', {'invoices': invoices})


@login_required
def products(request):
    products = Product.objects.all()

    return render(request, 'invoice/products.html', {'products': products})



@login_required
def clients(request):
    clients = Client.objects.all()

    if request.method == 'GET':
        form = ClientForm()
        user_form = UserForm()
        return render(request, 'invoice/clients.html', {'clients': clients,'form':form, 'user_form': user_form})

    if request.method == 'POST':
        user_form = UserForm(data=request.POST)
        form = ClientForm(request.POST, request.FILES)

        

        if user_form.is_valid() and form.is_valid():
            user = user_form.save()
            user.save()

            profile = form.save(commit=False)
            profile.user = user
            profile.save()

            messages.success(request, 'New Client Added')
            return redirect('clients')
        else:
            messages.error(request, 'Problem processing your request')
            return redirect('clients')
    else:
        user_form = UserForm()
        form = ClientForm()


    return render(request, 'invoice/clients.html', {'clients': clients,
                             'user_form':user_form,
                             'form':form})



@login_required
def logout(request):
    auth.logout(request)
    return redirect('login')


###--------------------------- Create Invoice Views Start here --------------------------------------------- ###

@login_required
def createInvoice(request):
    #create a blank invoice ....
    number = 'INV-'+str(uuid4()).split('-')[1]
    newInvoice = Invoice.objects.create(number=number)
    newInvoice.save()

    inv = Invoice.objects.get(number=number)
    return redirect('create-build-invoice', slug=inv.slug)




def createBuildInvoice(request, slug):
    #fetch that invoice
    try:
        invoice = Invoice.objects.get(slug=slug)
        pass
    except:
        messages.error(request, 'Something went wrong')
        return redirect('invoices')

    #fetch all the products - related to this invoice
    products = Product.objects.filter(invoice=invoice)


    context = {}
    context['invoice'] = invoice
    context['products'] = products

    if request.method == 'GET':
        prod_form  = ProductForm()
        inv_form = InvoiceForm(instance=invoice)
        client_form = ClientSelectForm(initial_client=invoice.client)
        context['prod_form'] = prod_form
        context['inv_form'] = inv_form
        context['client_form'] = client_form
        return render(request, 'invoice/create-invoice.html', context)

    if request.method == 'POST':
        prod_form  = ProductForm(request.POST)
        inv_form = InvoiceForm(request.POST, instance=invoice)
        client_form = ClientSelectForm(request.POST, initial_client=invoice.client, instance=invoice)

        if prod_form.is_valid():
            obj = prod_form.save(commit=False)
            obj.invoice = invoice
            obj.save()

            messages.success(request, "Invoice product added succesfully")
            return redirect('create-build-invoice', slug=slug)
        elif inv_form.is_valid and 'paymentTerms' in request.POST:
            inv_form.save()

            messages.success(request, "Invoice updated succesfully")
            return redirect('create-build-invoice', slug=slug)
        elif client_form.is_valid() and 'client' in request.POST:

            client_form.save()
            messages.success(request, "Client added to invoice succesfully")
            return redirect('create-build-invoice', slug=slug)
        else:
            context['prod_form'] = prod_form
            context['inv_form'] = inv_form
            context['client_form'] = client_form
            messages.error(request,"Problem processing your request")
            return render(request, 'invoice/create-invoice.html', context)


    return render(request, 'invoice/create-invoice.html', context)




def viewPDFInvoice(request, slug):
    #fetch that invoice
    try:
        invoice = Invoice.objects.get(slug=slug)
        pass
    except:
        messages.error(request, 'Something went wrong')
        return redirect('invoices')

    #fetch all the products - related to this invoice
    products = Product.objects.filter(invoice=invoice)


    #Calculate the Invoice Total
    invoiceCurrency = ''
    invoiceTotal = 0.0
    if len(products) > 0:
        for x in products:
            y = float(x.quantity) * float(x.price)
            invoiceTotal += y
            invoiceCurrency = x.currency

    return render(request, 'invoice/water-bill.html', {'invoice':invoice,'products': products,'invoiceTotal':"{:.2f}".format(invoiceTotal), 'invoiceCurrency': invoiceCurrency })



def deleteInvoice(request, slug):
    try:
        Invoice.objects.get(slug=slug).delete()
    except:
        messages.error(request, 'Something went wrong')
        return redirect('invoices')

    return redirect('invoices')































###
##
#
