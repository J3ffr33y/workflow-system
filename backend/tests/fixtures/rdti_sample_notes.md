# Project Thermo: technical notes for the 2025 income year

This is an invented example for trying the R&D report workbench. No client data.

It was unknown whether a low-cost sensor could hold 0.1 degree accuracy above 80 degrees. No supplier datasheet or published literature covered that range, so the outcome could not be determined in advance by a competent professional.

We hypothesised that model-predictive control with a thermal lag model would cut temperature overshoot below 2% compared with the existing PID controller.

We ran 40 experiment runs on a test rig at 60, 70 and 80 degrees with two sensor batches, sampling at 10 Hz. Each run lasted 30 minutes and was logged to the shared drive.

Measured results: overshoot fell from 6.4% to 1.7% across the 40 runs, while batch B sensors failed above 78 degrees.

We concluded the hypothesis was confirmed, and as a result we decided to drop batch B sensors from the design.

The new knowledge is that a thermal lag model makes low-cost sensors usable up to 80 degrees, which was not known before these runs.

We built a thermal test chamber to run the experiments above. The chamber was needed only to produce the controlled heat conditions for the core activity.

Overall the team successfully delivered an innovative and significantly improved product.
