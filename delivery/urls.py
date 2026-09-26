from django.urls import path
from .views import ListProduct,ListCategory,GetProduct,GetOrders,ListFilterCategory,ListFilterProduct,GetProfile,SaveToken,GetAdminToken,CreateContactUsView,GetOrdersForMonitor,GetDeliveryInfo,CheckAuth,UploadPaymentScreenshot,WeeklySalaryView,SalaryHistoryView,RateProductView,GiveawayDashboardView,SpinWheelStatusView,SpinWheelSpinView
from .auth_views import LoginView, CreateUserView, UpdatePhoneView


urlpatterns = [
    path("create-user/",CreateUserView.as_view(),name="create-user"),
    path("check-auth/",CheckAuth.as_view(),name="check-auth"),
    path("list-product/",ListProduct.as_view(),name="list-product"),
    path("list-category/",ListCategory.as_view(),name="list-category"),
    path("product-detail/<slug:slug>/",GetProduct.as_view(),name="list-category"),
    path("get-orders/",GetOrders.as_view(),name="get-orders"),
    path("get-orders-monitor/",GetOrdersForMonitor.as_view(),name="get-orders-for-monitor"),
    path("sub-products/",ListFilterProduct.as_view(),name="sub-products"),
    path("sub-categorys/",ListFilterCategory.as_view(),name="sub-categorys"),
    path("get-profile/",GetProfile.as_view(),name="get-profile"),
    path("save-token/",SaveToken.as_view(),name="save-token"),
    path("get-token/",GetAdminToken.as_view(),name="get-token"),
    path("contact-us/",CreateContactUsView.as_view(),name="contact-us"),
    path("get-delivery-info/",GetDeliveryInfo.as_view(),name="get-delivery-info"),
    path("orders/<int:pk>/upload-screenshot/",UploadPaymentScreenshot.as_view(),name="upload-payment-screenshot"),
    path("get-weekly-salary/",WeeklySalaryView.as_view(),name="weekly-salary"),
    path("get-salary-history/",SalaryHistoryView.as_view(),name="salary-history"),
    path("rate-product/<slug:slug>/",RateProductView.as_view(),name="rate-product"),
    path("auth/login/",        LoginView.as_view()), 
    path("auth/update-phone/", UpdatePhoneView.as_view()),
    path("giveaway-dashboard/", GiveawayDashboardView.as_view(), name="giveaway-dashboard"),
    path('spin-wheel/status/', SpinWheelStatusView.as_view(), name='spin-wheel-status'),
    path('spin-wheel/spin/', SpinWheelSpinView.as_view(), name='spin-wheel-spin'),
    
]

