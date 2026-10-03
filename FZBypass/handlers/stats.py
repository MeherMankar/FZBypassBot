from time import time
from asyncio import to_thread
from psutil import (
    cpu_count,
    cpu_percent,
    disk_usage,
    swap_memory,
    virtual_memory,
    Process,
)
from wzgram.filters import command, user, regex
from wzgram.types import InlineKeyboardButton, InlineKeyboardMarkup

from FZBypass import Config, Bypass, BOT_START
from FZBypass.core.bot_utils import (
    AuthChatsTopics,
    convert_time,
    get_readable_size,
    progress_bar,
)
from FZBypass.core.commands import BotCommands


def usable_cpus(proc):
    try:
        return len(proc.cpu_affinity())
    except Exception:
        return cpu_count(logical=True) or "N/A"


def bot_stats():
    proc = Process()
    memory = virtual_memory()
    swap = swap_memory()
    total, used, free, disk = disk_usage(".")
    bot_ram = proc.memory_info().rss
    cpu = cpu_percent(interval=0.5)
    cores = cpu_count(logical=True) or 0
    p_cores = cpu_count(logical=False) or 0
    msg = f"""⌬ <b><i>BOT STATISTICS :</i></b>
┖ <b>Bot Uptime :</b> {convert_time(time() - BOT_START)}

┎ <b><i>BOT RAM :</i></b>
┖ <b>Used :</b> {get_readable_size(bot_ram)}

┎ <b><i>SYSTEM RAM :</i></b>
┃ {progress_bar(memory.percent)} {memory.percent}%
┖ <b>U :</b> {get_readable_size(memory.used)} | <b>F :</b> {get_readable_size(memory.available)} | <b>T :</b> {get_readable_size(memory.total)}

┎ <b><i>SWAP MEMORY :</i></b>
┃ {progress_bar(swap.percent)} {swap.percent}%
┖ <b>U :</b> {get_readable_size(swap.used)} | <b>F :</b> {get_readable_size(swap.free)} | <b>T :</b> {get_readable_size(swap.total)}

┎ <b><i>CPU :</i></b>
┃ {progress_bar(cpu)} {cpu}%
┠ <b>Total Core(s) :</b> {cores} | <b>P-Core(s) :</b> {p_cores} | <b>V-Core(s) :</b> {cores - p_cores}
┖ <b>Usable CPU(s) :</b> {usable_cpus(proc)}

┎ <b><i>DISK :</i></b>
┃ {progress_bar(disk)} {disk}%
┖ <b>U :</b> {get_readable_size(used)} | <b>F :</b> {get_readable_size(free)} | <b>T :</b> {get_readable_size(total)}"""

    ws_stats = Config.WEBSHARE_MANAGER.stats()
    if ws_stats["total_keys"] > 0:
        msg += f"""\n\n┎ <b><i>WEBSHARE PROXIES :</i></b>
┠ <b>APIs Active :</b> {ws_stats['active_keys']} / {ws_stats['total_keys']}
┖ <b>Total Proxies :</b> {ws_stats['total_proxies']}"""
    return msg


@Bypass.on_message(
    command(BotCommands.StatsCommand) & (user(Config.OWNER_ID) | AuthChatsTopics)
)
async def send_stats(client, message):
    uid = message.from_user.id
    await message.reply(
        await to_thread(bot_stats),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Close", callback_data=f"stats {uid} close")]]
        ),
    )


@Bypass.on_callback_query(regex(r"^stats "))
async def stats_cb(client, query):
    _, owner, action = query.data.split()
    if query.from_user.id != int(owner):
        return await query.answer("Not Yours!", show_alert=True)
    if action == "close":
        await query.answer()
        await query.message.delete()
