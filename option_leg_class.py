from datetime import date

class OptionLeg:
    def __init__(self, buy_sell, option_type, quantity, strike_price, expiration_date, open_price):
        self.buy_sell = str(buy_sell)
        self.option_type = str(option_type)
        self.quantity = int(quantity)
        self.strike_price = float(strike_price)
        
        if isinstance(expiration_date, str):
            try:
                self.expiration_date = date.fromisoformat(expiration_date)
            except ValueError:
                raise ValueError(f"Invalid ISO format string for expiration_date: {expiration_date}")
        elif isinstance(expiration_date, date):
            self.expiration_date = expiration_date
        else:
            raise TypeError("expiration_date must be a date object or an ISO format string")
            
        self.open_price = float(open_price)
        self._class_marker = "OptionLeg" # For easier type identification during deserialization

    def to_dict(self):
        """Serializes the OptionLeg object to a dictionary, converting date to ISO string."""
        return {
            "buy_sell": self.buy_sell,
            "option_type": self.option_type,
            "quantity": self.quantity,
            "strike_price": self.strike_price,
            "expiration_date": self.expiration_date.isoformat(), # Convert date to string
            "open_price": self.open_price,
            "_class_marker_": self._class_marker 
        }

    @classmethod
    def from_dict(cls, data):
        """Deserializes a dictionary into an OptionLeg object, converting ISO string to date."""
        if not isinstance(data, dict) or data.get("_class_marker_") != "OptionLeg":
            # Raise an error or return None if the data isn't what's expected
            # For robustness, one might log a warning and try to proceed if some keys match,
            # but strict checking is safer for ensuring data integrity.
            raise ValueError("Data is not a valid OptionLeg dictionary.")

        exp_date_str = data.get("expiration_date")
        # expiration_date is expected to be an ISO string from to_dict
        # The __init__ method will handle conversion from string to date.
        
        return cls(
            buy_sell=data.get("buy_sell"),
            option_type=data.get("option_type"),
            quantity=data.get("quantity"),
            strike_price=data.get("strike_price"),
            expiration_date=exp_date_str, # Pass the string directly to __init__
            open_price=data.get("open_price")
        )

    def __repr__(self):
        exp_date_str = self.expiration_date.strftime('%Y-%m-%d') if self.expiration_date else "N/A"
        return (f"OptionLeg({self.quantity}x {self.buy_sell.capitalize()} {self.option_type.capitalize()} "
                f"K={self.strike_price:.2f} Exp:{exp_date_str} @{self.open_price:.2f})")

    def get_description(self, display_currency_func, display_date_func):
        """Returns a full descriptive string for the leg."""
        return (
            f"{self.quantity}x {str(self.buy_sell).capitalize()} "
            f"{str(self.option_type).capitalize()} "
            f"Strike: {display_currency_func(self.strike_price, '')} "
            f"Exp: {display_date_func(self.expiration_date)} "
            f"Open Price: {display_currency_func(self.open_price, '')}"
        )

    def get_brief_description(self, display_currency_func, display_date_func):
        """Returns a brief descriptive string for the leg, typically for summaries."""
        return (
            f"{self.quantity}x "
            f"{str(self.buy_sell).capitalize()} "
            f"{str(self.option_type).capitalize()} "
            f"{display_currency_func(self.strike_price, '')} "
            f"Exp: {display_date_func(self.expiration_date)}"
        )
