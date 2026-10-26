"""PetBot services: the composition roots, one per deployable.

``core`` = chat + command over the stateless skills; ``music`` = the voice
service. What differs between them is *composition* (installed skills, transport,
injected providers), not source organisation.
"""
