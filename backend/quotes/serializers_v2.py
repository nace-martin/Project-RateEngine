from rest_framework import serializers

class BuyOfferSerializer(serializers.Serializer):
    # This is a placeholder. A real implementation would serialize the BuyOffer dataclass.
    pass

class QuoteResponseSerializerSales(serializers.Serializer):
    is_incomplete = serializers.BooleanField()
    reason = serializers.CharField(required=False)
    quote_id = serializers.CharField(required=False)
    # Sales roles should not see BUY-side data

class QuoteResponseSerializerManager(serializers.Serializer):
    is_incomplete = serializers.BooleanField()
    reason = serializers.CharField(required=False)
    quote_id = serializers.CharField(required=False)
    best_buy_offer = BuyOfferSerializer()
    snapshot = serializers.DictField()
