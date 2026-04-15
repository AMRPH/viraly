from rest_framework.views import APIView
from rest_framework.response import Response
from .serializers import RegisterSerializer, CustomTokenObtainPairSerializer
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.mail import send_mail
from django.conf import settings
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.renderers import JSONRenderer
from rest_framework.permissions import IsAuthenticated, AllowAny
from users.serializers import UserSerializer

EMAIL = getattr(settings, 'EMAIL_HOST_USER')

User = get_user_model()

class RegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()

            token = RefreshToken.for_user(user).access_token
            verify_url = f"http://viraly.online/api/users/verify-email/?token={token}"
            
            send_mail(
                subject='Verify your email',
                message=f'Click to verify: {verify_url}',
                from_email=EMAIL,
                recipient_list=[user.email],
            )

            return Response({'detail': 'Verification email sent'}, status=201)
        return Response(serializer.errors, status=400)


class ResendVerificationView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'detail': 'Email is required'}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'detail': 'User not found'}, status=404)

        if user.is_email_verified:
            return Response({'detail': 'Email already verified'}, status=400)

        token = RefreshToken.for_user(user).access_token
        verify_url = f"http://viraly.online/api/users/verify-email/?token={token}"

        send_mail(
            subject='Verify your email',
            message=f'Click to verify: {verify_url}',
            from_email=EMAIL,
            recipient_list=[user.email],
        )

        return Response({'detail': 'Verification email resent'}, status=200)



class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]

    def get(self, request):
        token = request.GET.get('token')
        try:
            access_token = AccessToken(token)
            user = User.objects.get(id=access_token['user_id'])
            user.is_email_verified = True
            user.save()
            return Response({'detail': 'Email verified'}, status=200)
        except Exception as e:
            return Response({'detail': 'Invalid or expired token'}, status=400)
        

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class GetUserInfoAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response({'detail': serializer.data}, status=200)
