# rpi-rotary-encoder-python
I had a quick look for some clean code to listen to a rotary encoder attached to a Raspberry Pi, and didn't find any... so I rolled my own.

## Usage

First of all, you're going to need to instantiate an Encoder instance, and give it the two GPIO pins to listen on:

```python
from encoder import Encoder
e1 = Encoder(26, 19)
```

Now at any time you want, you can read the current value of the encoder as follows:

```python
value = e1.getValue()
```

OK, but what if you don't want to have to keep checking for a value change?  Instead, you can define a callback function that will be invoked whenever the value changes:

```python
from encoder import Encoder

def valueChanged(value):
    pass # Or do something useful with the value here!

e1 = Encoder(26, 19, callback=valueChanged)
```
Now your `valueChanged` function will be invoked whenever the encoder changes value (but only after it goes through the full quadrature cycle; bounces, partial turns etc will not be reported)

## Design Goals
I had a couple of important design goals in mind when I put this together:

* I wanted it to be as robust as possible, recognizing that a Pi running Raspbian is *not* a real-time system, so some events are going to get missed

* I wanted it to be efficient, because I have a battery-powered project in mind that will use this.  That means no polling of GPIOs; interrupts are the way to go.

I was using a fairly high quality [Bournes 24-pulse encoder from Adafruit](https://www.adafruit.com/product/377) when I developed it, and also tested it with a cheaper [Alpha 12-pulse encoder from Elmwood Elecronics](https://elmwoodelectronics.ca/products/9117), and it works fine with both.  It should work with just about any rotary encoder that uses the standard 2-phase quadrature encoding scheme.

The principle of operation is pretty straightforward; there are 4 possible states for the encoder outputs, which I refer to as:

* `00`: The "resting" position when the knob is in a detent and not being moved (although it's certainly possible for most encoders to rest in one or more of the other positions)
* `01`: The first state encountered as the encoder begins to turn clockwise (or "right", the way my brain thinks about it) from the resting position.  Alternatively, the last state encountered as the encoder completes a counter-clockwise (or "left") turn, just before it returns to the resting position
* `11`: The state halfway through a step in the encoder
* `10`: The first state encountered as the encoder begins to turn counter-clockwise from the resting position.  Alternatively, the last state encountered as the encoder completes a clockwise turn, just before it returns to the resting position

Given the above definitions, in an ideal world, one step clockwise would generate the sequence `00` -> `01` -> `11` -> `10` -> `00`, while one step counter-clockwise would result in `00` -> `10` -> `11` -> `01` -> `00`.

## State Machine Operation

The state machine records both the last-known position of the encoder, as well as the last-known direction of rotation, for reasons that will be explained below.  State transitions occur whenever inputs change, although not all state transitions result in a change in the output value.  

### Interrupts vs. Polling

The constructor sets up interrupts on both input pins for both rising and falling edge.  Whenever an edge is detected, the values of both pins are read to construct a new state, and then a state machine decides what to do based on the current state and the new state.  The interrupt handler does get passed the pin that changed state to trigger the interrupt, but the state machine needs to know both values, and we don't really know how promptly our interrupt got serviced, so the handler simply reads both input pins, regardless of which one triggered the interrupt.

What's important is that it takes no CPU cycles to wait on an interrupt - we're not polling; we're relying on a hardware notification to bring us back to life.  In contrast, a polling-based approach would take one core of our CPU close to 100% usage, and power consumption would go up dramatically!

### Debouncing

A rotary encoder is very likely to generate some bouncy signals, especially when being turned slowly.  The GPIO library includes optional debouncing periods on interrupts.  But I chose not to use them, and here's why: First of all, debounce works great on a button but not so well on an encoder because an encoder can legitimately generate pulses at the rate of a few Hz to possibly 100 Hz or so, if the knob is being spun pretty fast.  Adding a debounce delay would cause many of the pulses to be missed.

Just as importantly though, rotary encoders use a 2-bit Gray code to represent their output, meaning that in normal operation, only one bit changes at a time, but it takes 4 transitions to result in the output changing.

The state machine logic inhernently handles some bounce elimination. For example, if you start to turn the encoder slowly clockwise, it's quite likely you'll see the following sequence of values:

* `00`: In the rest state
* `01`: Just touched the first contact on the encoder ring
* `00`: Mechanical vibration or something else caused us to immediately lose contact
* `01`: Re-established contact with the first contact on the encoder ring

Assuming this happens at a pace the state machine can handle, the first transition causes the direction to be set to `R` (i.e. clockwise); the second transition reverses the direction to `L` and takes us back to the 00 state.  Either way no value change occurs, and the event is effectively rejected.

However the last transition re-established the direction as `R`, meaning that if we subsequently go through the `11`, `10`, and `00` states, it will still result in the output value increasing, despite the bouncing.

Now consider what happens if the user turns the encoder abruptly; we might see the following states:

* `00`: In the rest state
* `01`: Established motion clockwise
* `11`: Reached the midpoint of one step clockwise
* `00`: We must have either gone through `10` or `01` to get back to `00`, but we missed it due to timing.  However, knowing that we were previously moving clockwise, we can guess that we blasted through the `10` state, and still consider it a completed clockwise rotation.

All that being said, the logic of the state machine can be summed up as follows:
* If we detect a transition between two adjacent states, we know the new state, as well as the direction of rotation
* If we detect a transition to 00 and we know the direction of rotation, then we know to either increment or decrement the output value
