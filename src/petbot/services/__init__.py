"""PetBot services: the composition roots, one per deployable.

The only deployment-aware layer — each service wires the concept libraries (domain,
process, skills, platform) into a runnable :class:`~petbot.domain.process.Process` and
serves it. ``core`` = chat + command over the stateless skills; ``music`` = the voice
service. What differs between them is *composition* (installed skills, transport,
injected providers), not source organisation.
"""
