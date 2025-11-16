(Get-Content backend\quotes\serializers.py | Select-Object @{n='LineNumber';e={++\}}, @{n='Line';e={\}} | Format-Table -AutoSize | Out-String -Width 400)
