# Discord Pruner Bot

Discord Bot to Prune Inactive members. A work in progress.

## Goals/aims

### Setup

1. Create a "member" role that has the same permissions as @everyone.
2. Give all "active" people the "member" role.
3. Create a landing area (section/channel) for new members and explicitly change the @everyone permissions there.
4. Remove "Read Text Channels & See Voice Channels" permissions from @everyone.

This should leave @everone with access to only the welcome channel/section and other members access to everything else.

### Runtime

* The bot will auto-add the "member" role when a non-member talks in the welcome section.
* [TODO] On `!prune` and/or on a regular schedule, remove the "member" role from inactive members.
* [TODO] Add a trigger to add the "member" role to active members for setup.
* [TODO] Customize the inactive duration.

