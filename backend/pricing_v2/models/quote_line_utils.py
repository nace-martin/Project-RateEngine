# This file will contain utility functions or classes to interact with QuoteLine
# objects, preferring the 'side' field over 'is_buy'/'is_sell' booleans
# when QUOTER_V2_ENABLED is active.
#
# Example (future implementation):
#
# from quotes.models import QuoteLine
#
# def get_quote_line_side(quote_line: QuoteLine) -> str:
#     if hasattr(quote_line, 'side') and quote_line.side:
#         return quote_line.side
#     elif quote_line.is_buy:
#         return 'BUY'
#     elif quote_line.is_sell:
#         return 'SELL'
#     return 'UNKNOWN'