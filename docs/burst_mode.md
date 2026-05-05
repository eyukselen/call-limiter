# Burst Mode

## Burst Mode Enabled
If enabled by setting the parameter `allow_burst=True`, all calls allowed in the period will be fired instantly.

![Burst](assets/call-limiter-burst.gif)

## Burst Mode Disabled (Drip)
If disabled by setting the parameter `allow_burst=False`, all calls allowed in the period will be fired by spreading them evenly throughout the period.

![Drip](assets/call-limiter-drip.gif)