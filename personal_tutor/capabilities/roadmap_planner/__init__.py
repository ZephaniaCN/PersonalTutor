"""Personalized roadmap planner.

Given a learner profile (BKT mastery per KP) and a domain knowledge graph,
produces a learning roadmap: an ordered list of objectives that (1) respects
prerequisite dependencies (a KP is never scheduled before its prereqs are
mastered or scheduled), and (2) prioritizes weak points so the learner closes
gaps first. The roadmap is consumed by the REST ``/roadmaps`` endpoints and
(optionally) seeded into DeepTutor's Mastery Path as a Book.
"""
