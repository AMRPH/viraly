from django.urls import path
from users.views import RegisterView, VerifyEmailView, CustomTokenObtainPairView, ResendVerificationView, GetUserInfoAPIView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('register/', RegisterView.as_view()),
    path('resend-verification/', ResendVerificationView.as_view()),
    path('verify-email/', VerifyEmailView.as_view()),
    path('token/', CustomTokenObtainPairView.as_view()),
    path('token/refresh/', TokenRefreshView.as_view()),
    path('info/', GetUserInfoAPIView.as_view())
]
