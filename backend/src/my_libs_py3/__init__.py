import asyncio

# Ensure an event loop is set for the current context *before* any other imports from this package,
# especially those that might lead to importing ib_insync.
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import ib_insync.util # ib_insync includes nest_asyncio as a dependency

# Apply ib_insync's patch. This function call includes nest_asyncio.apply()
# and is generally needed for ib_insync to work correctly in environments like Streamlit.
ib_insync.util.patchAsyncio()

from .my_lib import *
from .my_strategies import *
from .my_trader import *
from .my_pair_trade import *
# from .mysql import *
from .pyfin import *
from .Robinhood import *
from .send_email import *
# from .ta_strategies import *
from .future import *
from .option import *
from .my_data import *
from .tdameritrade import *
from .TD_Order import *

