from app.modules.automations.engine import on_item_event
from app.platform.events.registry import Subscriber, subscribers

subscribers.register(
    Subscriber(name="automations.events", patterns=("item.created", "item.updated"), handler=on_item_event)
)
