## Logging Guidance (Optional)

Open this guide only when the user explicitly asks for custom logging behavior or log files.

Default behavior for generated scripts:
- Do not add custom logging setup.
- Keep BTC output at level INFO on STDOUT.

### When custom logging is requested

Configure handlers on the `btc_embedded` logger before creating `EPRestApi`.
The library adds its own console handler only when no handlers exist, so pre-configuring handlers allows controlling output destinations and format.

```python
import logging

logger = logging.getLogger('btc_embedded')
logger.setLevel(logging.INFO)

fmt = logging.Formatter(
    '[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

for handler in [
    logging.StreamHandler(),
    logging.FileHandler('results/test_run.log'),
]:
    handler.setFormatter(fmt)
    logger.addHandler(handler)
```

Use this pattern only when the user asks for file logging, custom formatting, or additional handlers.
Don't add obsolete log lines mentioning that a certain ep.(post|put|delete) action was called. Those methods already log what they are doing through their message field.
