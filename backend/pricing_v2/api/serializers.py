from rest_framework import serializers
from pricing_v2.dataclasses_v2 import Totals, CalcLine

class CalcLineSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=255)
    description = serializers.CharField(max_length=255)
    amount = serializers.FloatField()
    currency = serializers.CharField(max_length=3)

class TotalsSerializer(serializers.Serializer):
    invoice_ccy = serializers.CharField(max_length=3)
    is_incomplete = serializers.BooleanField()
    reasons = serializers.ListField(child=serializers.CharField(max_length=255))
    sell_subtotal = serializers.FloatField()
    sell_total = serializers.FloatField()
    sell_lines = CalcLineSerializer(many=True)
    buy_subtotal = serializers.FloatField()
    buy_total = serializers.FloatField()
    buy_lines = CalcLineSerializer(many=True)