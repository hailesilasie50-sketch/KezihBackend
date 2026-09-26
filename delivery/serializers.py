from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Profile, CategoryModel, ProductImage, ProductItem, Order, ContactUs, Giveaway, SpinWheelResult
from .models import SpinPrize  # add to your existing models import

User = get_user_model()   

class UserSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(write_only=True, required=False)
    is_delivery = serializers.BooleanField(write_only=True, required=False)
    chat_id = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'phone', 'is_delivery', 'chat_id']
        extra_kwargs = {
            "password": {"write_only": True}
        }

    def validate_password(self, value):
        if len(value) < 4:
            raise serializers.ValidationError("Password must be at least 4 characters.")
        return value

    def create(self, validated_data):
        phone = validated_data.pop("phone", None)
        is_delivery = validated_data.pop("is_delivery", None)
        chat_id = validated_data.pop("chat_id", None)

        user = User.objects.create_user(**validated_data)

        # Create profile with phone
        Profile.objects.create(
            user=user,
            phone=phone,
            is_delivery=is_delivery,
            chat_id=chat_id,
            name=user.username
        )
        return user



class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    class Meta:
        model = Profile
        fields = '__all__'

from rest_framework import serializers
from .models import CategoryModel

class CategorySerializer(serializers.ModelSerializer):
    category = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = CategoryModel
        fields = "__all__"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")

        if request and data.get("image"):
            data["image"] = request.build_absolute_uri(instance.image.url)
            data["image"] = data["image"].replace("http://", "https://")

        return data



class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = "__all__"

class ProductItemSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True,read_only=True)
    category = CategorySerializer(read_only=True)
    class Meta:
        model = ProductItem
        fields = "__all__"

class OrderSerializer(serializers.ModelSerializer):
    owner = ProfileSerializer(read_only=True)
    class Meta:
        model = Order
        fields = '__all__'

class ContactUsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactUs
        fields = "__all__"
        
        

class GiveawaySerializer(serializers.ModelSerializer):
    winner = serializers.SerializerMethodField()
 
    class Meta:
        model = Giveaway
        fields = ["id", "winner", "price", "milestone", "completed_at"]
 
    def get_winner(self, obj):
        if not obj.winner:
            return None
        return {
            "name": obj.winner.name or obj.winner.user.username,
            "phone": obj.winner.phone or "",
        }



class SpinPrizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpinPrize
        fields = ["id", "key", "label", "kind", "value", "spin_count", "color", "order"]


class SpinWheelResultSerializer(serializers.ModelSerializer):
    prize = SpinPrizeSerializer(read_only=True)
    winner_name = serializers.SerializerMethodField()

    class Meta:
        model = SpinWheelResult
        fields = ["id", "prize", "coins_awarded", "spins_awarded",
                  "free_delivery_awarded", "status", "winner_name", "spun_at"]

    def get_winner_name(self, obj):
        return obj.profile.name or obj.profile.user.username
