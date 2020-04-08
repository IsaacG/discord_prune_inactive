#!/bin/python

import collections
import datetime
import discord
import enum
import os
import sys

from discord.ext import commands


async def is_owner(ctx):
  return ctx.guild and ctx.guild.owner == ctx.author


class Pruner(commands.Cog):
  """Member management to remove inactive and grant access on activity."""

  qualified_name = 'Prune Inactive Accounts'
  # None for no greeting, otherwise the welcome channel.
  GREET = 'welcome'
  MEMBER_ROLE = 'member'

  # How many messages to pull up from history per channel.
  # How many days since last activity before being deemed inactive.
  PRUNE_CHANNEL_HISTORY = 2000
  PRUNE_INACTIVE_TIMEOUT = 21

  def __init__(self):
    super(Pruner, self).__init__()
    self.member_role = None
    self.welcome_channel = None

  def get_nonmembers(self, guild):
    if not self.member_role:
      self.member_role = [r for r in guild.roles if r.name == self.MEMBER_ROLE][0]
    return [m for m in guild.members if self.member_role not in m.roles]

  def get_welcome_channel(self, guild):
    if self.GREET is None:
      return None
    if not self.welcome_channel:
      self.welcome_channel = [
          t for t in guild.text_channels if t.name == self.GREET][0]
    return self.welcome_channel

  @commands.Cog.listener()
  async def on_member_join(self, member):
    wc = self.get_welcome_channel(member.guild)
    if wc is None:
      return
    await wc.send(
        'Welcome, %s. Please introduce yourself to gain access to the rest of the server.' % member.mention)

  @commands.Cog.listener()
  async def on_message(self, message):
    if not self.member_role:
      self.member_role = [r for r in message.guild.roles if r.name == self.MEMBER_ROLE][0]

    if not message.guild:  # Direct message.
      pass
    elif message.is_system():
      pass
    elif isinstance(message.author, discord.User):
      pass
    elif self.member_role not in message.author.roles:
      await message.author.add_roles(self.member_role)

  @commands.command()
  @commands.check(is_owner)
  async def list_nonmembers(self, ctx, *args):
    nonmembers = self.get_nonmembers(ctx.guild)
    await ctx.send('%d non-members: %s' % (
        len(nonmembers), ', '.join(m.display_name for m in nonmembers)))

  @commands.command()
  @commands.check(is_owner)
  async def ping_nonmembers(self, ctx, *args):
    nonmembers = self.get_nonmembers(ctx.guild)
    await self.get_welcome_channel(ctx.guild).send('^^ %s' % ', '.join(m.mention for m in nonmembers))

  @commands.command()
  @commands.check(is_owner)
  async def prune(self, ctx, *args):
    if not self.member_role:
      self.member_role = [r for r in ctx.guild.roles if r.name == self.MEMBER_ROLE][0]

    channel_history_msgs = self.PRUNE_CHANNEL_HISTORY
    inactive_timeout = self.PRUNE_INACTIVE_TIMEOUT

    # Compute the last_spoke for all members across all channels.
    last_spoke = collections.defaultdict(lambda: datetime.datetime(1990, 1, 1))
    for channel in ctx.guild.text_channels:
      if not channel.permissions_for(ctx.guild.me).read_message_history:
        continue
      async for message in channel.history(limit=channel_history_msgs, oldest_first=False):
        last_spoke[message.author] = max(
            last_spoke[message.author], message.created_at)

    # Bucket users.
    silent_lurker = []  # Never spoke.
    less_active   = []  # Spoke but not for a long while.
    active        = []  # Spoke recently.

    now = datetime.datetime.now()
    for member in ctx.guild.members:
      if member not in last_spoke:
        silent_lurker.append(member)
      else:
        silent_since = now - last_spoke[member]
        if silent_since > datetime.timedelta(days=inactive_timeout):
          less_active.append(member)
        else:
          active.append(member)  # recently active
    print('%d members, %d silent lurkers, %d less active, %d active' % (len(ctx.guild.members), len(silent_lurker), len(less_active), len(active)))
    await ctx.send('%d members, %d silent lurkers, %d less active, %d active' % (len(ctx.guild.members), len(silent_lurker), len(less_active), len(active)))

    # Grant the "member" role to any active users.
    if False:
      for member in active:
        if self.member_role not in member.roles:
          await member.add_roles(self.member_role)
      print('Done adding members')

    # Remove the "member" role from inactive people.
    drop = []
    for member in less_active + silent_lurker:
      if self.member_role in member.roles:
        drop.append(member)
    await ctx.send('Drop "member" role from %d members.' % len(drop))
    if False:
      for member in drop:
        await member.remove_roles(self.member_role)
      print('Done removing members')


def main():
  bot = commands.Bot(command_prefix='!')
  bot.add_cog(Pruner())
  bot.run(os.getenv('DISCORD_TOKEN'))


if __name__ == '__main__':
  main()

# vim:ts=2:sw=2:expandtab
