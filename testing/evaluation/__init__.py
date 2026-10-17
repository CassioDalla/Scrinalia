"""
The benches that measure the AI against labelled collection data.

The package is nearly empty on purpose — each bench is a script with its own entry point. It holds
the one rule the benches share about when a metric is allowed to be printed at all.
"""

#: Below this many labelled positives a class's F1 is noise wearing a number's clothes, and the
#: report says "não medida" instead. Measured on this collection: five typologies have two examples
#: or none at all, and a "F1 = 1.000" built on two rows would be quoted as if it meant something.
#: The typology bench applies it per typology and the validator bench per rule, because both score a
#: *class* over a set where some classes are rare.
MIN_POSITIVES = 5
