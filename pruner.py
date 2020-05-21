#!/bin/python

import collections
import datetime
import discord
import enum
import json
import more_itertools
import os
import sys
import time

from discord.ext import commands


async def is_owner(ctx):
  return ctx.guild and ctx.guild.owner == ctx.author


async def role_permission(ctx):
  channel = ctx.message.channel
  return ctx.guild and channel.permissions_for(ctx.guild.me).manage_roles


class Pruner(commands.Cog):
  """Member management to remove inactive and grant access on activity."""

  qualified_name = 'Prune Inactive Accounts'
  # None for no greeting, otherwise the welcome channel.
  GREET = 'welcome'
  MEMBER_ROLE = 'member'

  # How many days since last activity before being deemed inactive.
  PRUNE_INACTIVE_TIMEOUT = 21
  PRUNE_KICK_TIMEOUT = 30

  def __init__(self):
    super(Pruner, self).__init__()
    self.member_role = None
    self.welcome_channel = None
    self.load_history()
    self.next_save = int(time.time()) + 60 * 60

  def cog_unload(self):
    self.save_history()

  def history_file(self):
    return os.getenv('PRUNER_HISTFILE')

  def load_history(self):
    if not os.path.exists(self.history_file()):
      self.history = {}
      return
    with open(self.history_file(), 'rt') as f:
      try:
        self.history = {int(k): v for k, v in json.load(f).items()}
      except Exception:
        self.history = {}

  def save_history(self):
    with open(self.history_file(), 'wt') as f:
      json.dump(self.history, f)
    self.next_save = int(time.time()) + 60 * 60

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
  @commands.check(role_permission)
  async def on_member_join(self, member):
    wc = self.get_welcome_channel(member.guild)
    if wc is None:
      return
    await wc.send(
        'Welcome, %s. Please introduce yourself to gain access to the rest of the server.' % member.mention)

  @commands.Cog.listener()
  @commands.check(role_permission)
  async def on_message(self, message):
    if not self.member_role:
      roles = [r for r in message.guild.roles if r.name == self.MEMBER_ROLE]
      if not roles:
        return
      self.member_role = roles[0]

    if (not message.guild  # Direct message.
        or message.is_system()
        or isinstance(message.author, discord.User)):
      return

    m_id = message.author.id
    now = int(time.time())
    first = m_id not in self.history
    self.history[m_id] = now

    if self.member_role not in message.author.roles:
      await message.author.add_roles(self.member_role)

    if first or now > self.next_save:
      self.save_history()

  @commands.command()
  @commands.check(is_owner)
  async def list_nonmembers(self, ctx, *args):
    nonmembers = self.get_nonmembers(ctx.guild)
    await ctx.send('%d non-members: %s' % (
        len(nonmembers), ', '.join(m.display_name for m in nonmembers)))

  @commands.command()
  @commands.check(is_owner)
  async def ping_nonmembers(self, ctx, *args):
    msg = ctx.message.content[len(ctx.prefix + ctx.invoked_with):].strip()
    if len(msg) >= 2000:
      await ctx.send('Message len is too big. %d > 2000. Fail.' % len(msg))
      return

    nonmembers = self.get_nonmembers(ctx.guild)
    out = '%s: %s' % (', '.join(m.mention for m in nonmembers), msg)
    if len(out) < 2000:
      await self.get_welcome_channel(ctx.guild).send(out)
      return

    await ctx.send('Message len is too big. %d > 2000. Chunking.' % len(out))
    people = ', '.join(m.mention for m in nonmembers)
    if len(people) < 2000:
      await self.get_welcome_channel(ctx.guild).send(people)
      await self.get_welcome_channel(ctx.guild).send(msg)
      return

    people = [', '.join(m.mention for m in subset) for subset in more_itertools.chunked(nonmembers, 50)]
    if any(len(p) > 2000 for p in people):
      await ctx.send('People list too big even in chunks. Fail.')
    for p in people:
      await self.get_welcome_channel(ctx.guild).send(p)
    await self.get_welcome_channel(ctx.guild).send(msg)

  @commands.command()
  @commands.check(is_owner)
  async def prune(self, ctx, *args):
    if not self.member_role:
      self.member_role = [r for r in ctx.guild.roles if r.name == self.MEMBER_ROLE][0]

    inactive_timeout = self.PRUNE_INACTIVE_TIMEOUT * 60 * 60 * 24
    now = int(time.time())
    dt_now = datetime.datetime.now()
    cutoff = now - inactive_timeout

    active = lambda m: (self.history.get(m.id, 0) > cutoff)

    never_spoke = [m for m in ctx.guild.members if m.id not in self.history]
    active      = [m for m in ctx.guild.members if active(m)]
    inactive    = list(set(ctx.guild.members) - set(never_spoke) - set(active))

    inactive_w_role = [m for m in inactive if self.member_role in m.roles]
    never_spoke_wr = [m for m in never_spoke if self.member_role in m.roles]
    drops = inactive_w_role + never_spoke_wr

    # People that joined a while ago and never spoke. Stale accounts. Kick?
    stale_cutoff = dt_now - datetime.timedelta(days=self.PRUNE_KICK_TIMEOUT)
    stale = [m for m in never_spoke if m.joined_at < stale_cutoff]

    await ctx.send('%d members, %d never spoke, %d inactive, %d active' % (len(ctx.guild.members), len(never_spoke), len(inactive), len(active)))
    await ctx.send('role_remove: Drop member from %d never spoke and %d inactive' % (len(never_spoke_wr), len(inactive_w_role)))
    await ctx.send(' '.join(m.display_name for m in drops))
    await ctx.send('kick_stale: Kick %d people that are stale (been here %d days and never spoke): %s' % (
        len(stale), self.PRUNE_KICK_TIMEOUT, ' '.join(m.display_name for m in stale)))

    if 'role_remove' in ctx.message.content.split():
      for member in drops:
        await member.remove_roles(self.member_role)
    if 'kick_stale' in ctx.message.content.split():
      for member in stale:
        await member.kick()
    await ctx.send('Done')

  @commands.command()
  @commands.check(is_owner)
  async def build_hist(self, ctx, *args):
    last_spoke = collections.defaultdict(lambda: datetime.datetime(1990, 1, 1))
    for channel in ctx.guild.text_channels:
      if not channel.permissions_for(ctx.guild.me).read_message_history:
        continue
      async for message in channel.history(limit=10000, oldest_first=False):
        if message.is_system() or isinstance(message.author, discord.User):
          continue
        last_spoke[message.author] = max(
            last_spoke[message.author], message.created_at)
    history = {}
    for m, dt in last_spoke.items():
      dt = dt.replace(tzinfo=datetime.timezone(datetime.timedelta()))
      history[m.id] = int(dt.timestamp())
    self.history = history
    self.save_history()
    await ctx.send('Done. Built history with %d members.' % len(self.history))

    # Grant the "member" role to any active users.
    if False:
      for member in active:
        if self.member_role not in member.roles:
          await member.add_roles(self.member_role)
      print('Done adding members')


def main():
  bot = commands.Bot(command_prefix='!')
  bot.add_cog(Pruner())
  bot.run(os.getenv('DISCORD_TOKEN'))


if __name__ == '__main__':
  main()

# vim:ts=2:sw=2:expandtab
