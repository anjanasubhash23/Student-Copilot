"""The learning loop: diagnostic, practice and explain mode, on top of the topic graph and the learner model.

Each step is an explicit function rather than a LangGraph state machine: the API already separates the
steps (start, answer, next), so there is no conversation state for an agent framework to manage.
"""
