import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiosqlite
import datetime
import os
from dotenv import load_dotenv

# Загружаем токен из .env файла
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "1022577394520961184"))
AFK_CHANNEL_ID = int(os.getenv("AFK_CHANNEL_ID", "1444411445608583372"))
AFK_GUILD_ID = int(os.getenv("AFK_GUILD_ID", "1444423438382006433"))
SUPPORT_ROLE_ID = int(os.getenv("SUPPORT_ROLE_ID", "1444005551628353587"))
BROADCAST_ROLE_ID = int(os.getenv("BROADCAST_ROLE_ID", "1444005594985005207"))
WARNS_LOG_CHANNEL_ID = int(os.getenv("WARNS_LOG_CHANNEL_ID", "1234567890123456789"))
TICKETS_CATEGORY_ID = int(os.getenv("TICKETS_CATEGORY_ID", "1234567890123456789"))

if not TOKEN:
    raise ValueError("DISCORD_TOKEN не найден в .env файле!")

# ---------- VIEW ДЛЯ INFO ----------

class InfoView(discord.ui.View):
    def __init__(self, bot_instance, user: discord.User):
        super().__init__(timeout=None)
        self.bot_instance = bot_instance
        self.user = user

    @discord.ui.button(label="Help", style=discord.ButtonStyle.blurple)
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        perms = interaction.user.guild_permissions if isinstance(interaction.user, discord.Member) else None
        commands_list = []
        commands_list.append("📚 Общие команды")
        commands_list.append("• /help — Справка по всем командам")
        commands_list.append("• /afk — Установить статус АФК")
        commands_list.append("• /afklist — Список людей в АФК")
        commands_list.append("• /unafk — Убрать себя из АФК")
        commands_list.append("• /warninfo — Посмотреть варны")
        commands_list.append("")
        if perms and perms.administrator:
            commands_list.append("🔐 Команды администратора")
            commands_list.append("• /warn — Выдать варн")
            commands_list.append("• /dwarn — Удалить варн по ID")
            commands_list.append("• /ban — Забанить пользователя")
            commands_list.append("• /unban — Разбанить пользователя")
            commands_list.append("• /timeout — Выдать мут")
            commands_list.append("• /untimeout — Снять мут")
            commands_list.append("• /kick — Выгнать пользователя")
            commands_list.append("• /broadcast — Отправить сообщение")

        help_text = "\n".join(commands_list)
        embed = discord.Embed(
            title="📖 Справка по командам",
            description=help_text,
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Показаны только доступные тебе команды")
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="← Вернуться", style=discord.ButtonStyle.gray, custom_id="back_to_info"))
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="AFK", style=discord.ButtonStyle.gray)
    async def afk_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AFKModal(self.bot_instance))

    @discord.ui.button(label="Ticket", style=discord.ButtonStyle.success)
    async def ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal(self.bot_instance))

class AFKModal(discord.ui.Modal, title="Установить статус АФК"):
    reason = discord.ui.TextInput(
        label="Причина АФК",
        placeholder="Например: работа, учёба, сон...",
        required=True,
        max_length=200
    )
    return_time = discord.ui.TextInput(
        label="Через сколько минут вернёшься?",
        placeholder="Например: 60 (1 час), 120 (2 часа)",
        required=True,
        max_length=10
    )

    def __init__(self, bot_instance):
        super().__init__()
        self.bot_instance = bot_instance

    async def on_submit(self, interaction: discord.Interaction):
        try:
            try:
                minutes = int(self.return_time.value)
                if minutes <= 0 or minutes > 1440:
                    await interaction.response.send_message(
                        "Ошибка: укажите время от 1 до 1440 минут (24 часа).",
                        ephemeral=True,
                        delete_after=180
                    )
                    return
            except ValueError:
                await interaction.response.send_message(
                    "Ошибка: время должно быть числом.",
                    ephemeral=True,
                    delete_after=180
                )
                return

            afk_guild = self.bot_instance.get_guild(AFK_GUILD_ID)
            if afk_guild:
                try:
                    member = afk_guild.get_member(interaction.user.id)
                    if member:
                        afk_channels = [ch for ch in afk_guild.voice_channels if ch.name.lower().startswith('afk')]
                        if afk_channels:
                            try:
                                await member.move_to(afk_channels[0])
                            except:
                                pass
                except:
                    pass

            now = datetime.datetime.now()
            return_time = now + datetime.timedelta(minutes=minutes)
            await self.bot_instance.db.execute(
                "INSERT OR REPLACE INTO afk_users (user_id, reason, afk_time, return_time) VALUES (?, ?, ?, ?)",
                (interaction.user.id, self.reason.value, now.isoformat(), return_time.isoformat())
            )
            await self.bot_instance.db.commit()

            await interaction.response.send_message(
                "Твой АФК статус установлен.",
                ephemeral=True,
                delete_after=180
            )
        except Exception as e:
            await interaction.response.send_message(
                f"Ошибка при установке АФК: {str(e)}",
                ephemeral=True,
                delete_after=180
            )
            print(f"Ошибка в AFKModal: {e}")

class TicketModal(discord.ui.Modal, title="Создать тикет"):
    reason = discord.ui.TextInput(
        label="Причина обращения",
        placeholder="Примеры: повышение, снятие варна, жалоба на игрока...",
        required=True,
        max_length=500
    )
    description = discord.ui.TextInput(
        label="Подробное описание",
        placeholder="Опишите вашу проблему подробнее...",
        required=True,
        max_length=1000,
        style=discord.TextStyle.long
    )

    def __init__(self, bot_instance):
        super().__init__()
        self.bot_instance = bot_instance

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            category = guild.get_channel(TICKETS_CATEGORY_ID) if TICKETS_CATEGORY_ID else None
            support_role = guild.get_role(SUPPORT_ROLE_ID)

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            }
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

            ticket_channel = await guild.create_text_channel(
                name=f"ticket-{interaction.user.name}",
                category=category,
                overwrites=overwrites
            )

            embed = discord.Embed(
                title="🎫 Новый тикет",
                color=discord.Color.blurple()
            )
            embed.add_field(name="Пользователь", value=interaction.user.mention, inline=True)
            embed.add_field(name="ID", value=interaction.user.id, inline=True)
            embed.add_field(name="Причина", value=self.reason.value, inline=False)
            embed.add_field(name="Описание", value=self.description.value, inline=False)
            embed.add_field(name="Время создания", value=discord.utils.format_dt(datetime.datetime.now(), style='F'), inline=False)
            embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)

            mention_text = ""
            if support_role:
                mention_text = f"{support_role.mention} "

            await ticket_channel.send(
                f"{mention_text}{interaction.user.mention}",
                embed=embed,
                view=TicketView()
            )

            await interaction.followup.send(
                f"Тикет создан: {ticket_channel.mention}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"Ошибка при создании тикета: {str(e)}",
                ephemeral=True
            )
            print(f"Ошибка в TicketModal: {e}")

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Закрыть тикет", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            await interaction.channel.delete()
        except:
            await interaction.response.send_message("Ошибка при удалении канала.", ephemeral=True)

    @discord.ui.button(label="Позвать администратора", style=discord.ButtonStyle.primary)
    async def call_admin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild = interaction.guild
        support_role = guild.get_role(SUPPORT_ROLE_ID)
        if support_role:
            await interaction.channel.send(f"{support_role.mention} — администратор вызван!")
        else:
            await interaction.channel.send("Ошибка: роль поддержки не найдена.")

class BroadcastModal(discord.ui.Modal, title="Отправить сообщение"):
    message = discord.ui.TextInput(
        label="Текст сообщения",
        placeholder="Введите сообщение...",
        required=True,
        max_length=2000
    )
    repeat_count = discord.ui.TextInput(
        label="Сколько раз отправить?",
        placeholder="Введите число (например: 1, 5, 10)",
        required=True,
        max_length=4
    )
    channel_id = discord.ui.TextInput(
        label="ID канала для отправки",
        placeholder="Например: 1234567890123456789",
        required=True,
        max_length=20
    )

    def __init__(self, bot_instance):
        super().__init__()
        self.bot_instance = bot_instance

    async def on_submit(self, interaction: discord.Interaction):
        try:
            try:
                repeat = int(self.repeat_count.value)
                channel_id = int(self.channel_id.value)
            except ValueError:
                await interaction.response.send_message(
                    "Ошибка: ID канала и количество должны быть числами.",
                    ephemeral=True,
                    delete_after=180
                )
                return

            if repeat <= 0 or repeat > 100:
                await interaction.response.send_message(
                    "Ошибка: количество должно быть от 1 до 100.",
                    ephemeral=True,
                    delete_after=180
                )
                return

            channel = interaction.guild.get_channel(channel_id)
            if not channel:
                await interaction.response.send_message(
                    "Ошибка: канал не найден. Проверьте ID.",
                    ephemeral=True,
                    delete_after=180
                )
                return

            await interaction.response.defer(ephemeral=True)

            for i in range(repeat):
                try:
                    await channel.send(self.message.value)
                    if i < repeat - 1:
                        await commands.sleep(0.5)
                except Exception as e:
                    print(f"Ошибка при отправке сообщения {i+1}: {e}")

            embed = discord.Embed(
                title="✅ Broadcast выполнен",
                description=f"Сообщение отправлено {repeat} раз в канал <#{channel_id}>",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(
                f"Ошибка при отправке сообщений: {str(e)}",
                ephemeral=True,
                delete_after=180
            )
            print(f"Ошибка в BroadcastModal: {e}")

# ---------- БОТ И БД ----------

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.synced = False
        self.db = None
        self.afklist_message = None
        self.afklist_channel = None

    async def setup_hook(self):
        self.db = await aiosqlite.connect("shizobot.db")
        await self.db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            joined_at TIMESTAMP,
            notes TEXT
        )
        """)
        await self.db.execute("""
        CREATE TABLE IF NOT EXISTS warns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            admin_id INTEGER,
            violation_type TEXT,
            timestamp TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
        """)
        await self.db.execute("""
        CREATE TABLE IF NOT EXISTS afk_users (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            afk_time TIMESTAMP,
            return_time TIMESTAMP
        )
        """)
        await self.db.commit()

    async def on_ready(self):
        await self.wait_until_ready()
        if not self.synced:
            try:
                await self.tree.sync(guild=discord.Object(id=GUILD_ID))
                self.synced = True
                print(f"Команды синхронизированы для гильдии {GUILD_ID}")
            except Exception as e:
                print(f"Ошибка синхронизации команд: {e}")
        print(f"Бот {self.user} запущен и готов к работе!")
        self.cleanup_afk_list.start()
        self.update_afk_panel.start()

    async def close(self):
        if self.db:
            await self.db.close()
        await super().close()

    @tasks.loop(minutes=1)
    async def cleanup_afk_list(self):
        """Удаляет пользователей из АФК списка, если их время истекло"""
        try:
            now = datetime.datetime.now()
            await self.db.execute(
                "DELETE FROM afk_users WHERE return_time <= ?",
                (now.isoformat(),)
            )
            await self.db.commit()
        except Exception as e:
            print(f"Ошибка при очистке АФК списка: {e}")

    @tasks.loop(minutes=1)
    async def update_afk_panel(self):
        """Обновляет АФК панель каждую минуту"""
        if not self.afklist_message or not self.afklist_channel:
            return
        
        try:
            async with self.db.execute(
                "SELECT user_id, reason, afk_time, return_time FROM afk_users ORDER BY return_time ASC"
            ) as cursor:
                afk_data = await cursor.fetchall()

            if not afk_data:
                embed = discord.Embed(
                    title="📋 АФК Панель",
                    description="В АФК никого нет!",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Обновлено: {datetime.datetime.now().strftime('%H:%M:%S')}")
                await self.afklist_message.edit(embed=embed)
                return

            table_lines = []
            table_lines.append("```")
            table_lines.append("╔═══════════════════════════════════════════════════════════════╗")
            table_lines.append("║              📋 СПИСОК ПОЛЬЗОВАТЕЛЕЙ В АФК                   ║")
            table_lines.append("╠═══════════════════════════════════════════════════════════════╣")
            
            for user_id, reason, afk_time, return_time in afk_data:
                try:
                    user = await self.fetch_user(user_id)
                    user_name = user.name[:15]
                except:
                    user_name = "Unknown"

                dt_return = datetime.datetime.fromisoformat(return_time)
                now = datetime.datetime.now()
                remaining = dt_return - now

                if remaining.total_seconds() > 0:
                    hours = int(remaining.total_seconds() // 3600)
                    mins = int((remaining.total_seconds() % 3600) // 60)
                    time_left = f"{hours}ч {mins}м" if hours > 0 else f"{mins}м"
                else:
                    time_left = "Скоро вернётся"

                reason_short = reason[:25] if len(reason) <= 25 else reason[:22] + "..."
                
                table_lines.append(f"║ 👤 {user_name:<15} │ ⏱️ {time_left:<12} ║")
                table_lines.append(f"║    📝 {reason_short:<49} ║")
                table_lines.append("║───────────────────────────────────────────────────────────────║")

            table_lines.append("╚═══════════════════════════════════════════════════════════════╝")
            table_lines.append("```")

            embed = discord.Embed(
                title="📋 АФК Панель",
                description="\n".join(table_lines),
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"Обновлено: {datetime.datetime.now().strftime('%H:%M:%S')} | Всего в АФК: {len(afk_data)}")
            
            await self.afklist_message.edit(embed=embed)
        except Exception as e:
            print(f"Ошибка при обновлении АФК панели: {e}")

bot = MyBot()

# ---------- ОБРАБОТЧИК КНОПОК ----------

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        if interaction.data.get("custom_id") == "back_to_info":
            embed = discord.Embed(
                title="ShizoBot",
                description="Привет, боец!\n\nЭто ShizoBot — разработан специально для SHIZORAGE FAMQ.\n\nДля продолжения определись, что тебе необходимо.",
                color=discord.Color.blurple()
            )
            embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else bot.user.default_avatar.url)
            embed.set_footer(text="ShizoBot v3.0 | 2025")
            view = InfoView(bot, interaction.user)
            await interaction.response.edit_message(embed=embed, view=view)

# ---------- КОМАНДА /HELP ----------

@bot.tree.command(
    name="help",
    description="Справка по всем доступным командам",
    guild=discord.Object(id=GUILD_ID)
)
async def help_cmd(interaction: discord.Interaction):
    try:
        perms = interaction.user.guild_permissions if isinstance(interaction.user, discord.Member) else None
        commands_list = []
        commands_list.append("📚 Общие команды")
        commands_list.append("• /help — Справка по всем командам")
        commands_list.append("• /afk — Установить статус АФК")
        commands_list.append("• /afklist — Список людей в АФК")
        commands_list.append("• /unafk — Убрать себя из АФК")
        commands_list.append("• /warninfo — Посмотреть варны")
        commands_list.append("")

        if perms and perms.administrator:
            commands_list.append("🔐 Команды администратора")
            commands_list.append("• /warn — Выдать варн")
            commands_list.append("• /dwarn — Удалить варн по ID")
            commands_list.append("• /ban — Забанить пользователя")
            commands_list.append("• /unban — Разбанить пользователя")
            commands_list.append("• /timeout — Выдать мут")
            commands_list.append("• /untimeout — Снять мут")
            commands_list.append("• /kick — Выгнать пользователя")
            commands_list.append("• /broadcast — Отправить сообщение")

        help_text = "\n".join(commands_list)
        embed = discord.Embed(
            title="📖 Справка по командам",
            description=help_text,
            color=discord.Color.blurple()
        )
        embed.set_footer(text="ShizoBot v3.0 | Показаны только доступные тебе команды")
        await interaction.response.send_message(embed=embed, ephemeral=True, delete_after=180)
    except Exception as e:
        await interaction.response.send_message(
            "Ошибка при загрузке справки.",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в help_cmd: {e}")

# ---------- КОМАНДА /INFO ----------

@bot.tree.command(
    name="info",
    description="Информация о боте и справка по командам",
    guild=discord.Object(id=GUILD_ID)
)
async def info(interaction: discord.Interaction):
    try:
        embed = discord.Embed(
            title="ShizoBot",
            description="Привет, боец!\n\nЭто ShizoBot — разработан специально для SHIZORAGE FAMQ.\n\nДля продолжения определись, что тебе необходимо.",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else bot.user.default_avatar.url)
        embed.set_footer(text="ShizoBot v3.0 | 2025")
        view = InfoView(bot, interaction.user)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(
            "Ошибка при загрузке информации.",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в info: {e}")

# ---------- КОМАНДА /AFK ----------

@bot.tree.command(
    name="afk",
    description="Установить статус АФК с подробной информацией",
    guild=discord.Object(id=GUILD_ID)
)
async def afk(interaction: discord.Interaction, reason: str = None, minutes: int = None):
    try:
        if reason is None or minutes is None:
            await interaction.response.send_modal(AFKModal(bot))
            return

        if minutes <= 0 or minutes > 1440:
            await interaction.response.send_message(
                "Ошибка: укажите время от 1 до 1440 минут (24 часа).",
                ephemeral=True,
                delete_after=180
            )
            return

        now = datetime.datetime.now()
        return_time = now + datetime.timedelta(minutes=minutes)
        await bot.db.execute(
            "INSERT OR REPLACE INTO afk_users (user_id, reason, afk_time, return_time) VALUES (?, ?, ?, ?)",
            (interaction.user.id, reason, now.isoformat(), return_time.isoformat())
        )
        await bot.db.commit()

        await interaction.response.send_message(
            "Твой АФК статус установлен.",
            ephemeral=True,
            delete_after=180
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Ошибка при установке АФК: {str(e)}",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в afk: {e}")

# ---------- КОМАНДА /UNAFK ----------

@bot.tree.command(
    name="unafk",
    description="Убрать себя из АФК списка",
    guild=discord.Object(id=GUILD_ID)
)
async def unafk(interaction: discord.Interaction):
    try:
        async with bot.db.execute(
            "SELECT user_id FROM afk_users WHERE user_id = ?",
            (interaction.user.id,)
        ) as cursor:
            result = await cursor.fetchone()

        if not result:
            await interaction.response.send_message(
                "Ты не находишься в АФК списке.",
                ephemeral=True,
                delete_after=180
            )
            return

        await bot.db.execute(
            "DELETE FROM afk_users WHERE user_id = ?",
            (interaction.user.id,)
        )
        await bot.db.commit()

        await interaction.response.send_message(
            "Ты убран из АФК списка.",
            ephemeral=True,
            delete_after=180
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Ошибка при удалении из АФК: {str(e)}",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в unafk: {e}")

# ---------- КОМАНДА /AFKLIST ----------

@bot.tree.command(
    name="afklist",
    description="Список пользователей в АФК (только для администраторов)",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.checks.has_permissions(administrator=True)
async def afklist(interaction: discord.Interaction):
    try:
        if bot.afklist_message is not None:
            await interaction.response.send_message(
                "АФК панель уже создана! Используй её же для обновлений.",
                ephemeral=True,
                delete_after=180
            )
            return

        await interaction.response.defer()

        async with bot.db.execute(
            "SELECT user_id, reason, afk_time, return_time FROM afk_users ORDER BY return_time ASC"
        ) as cursor:
            afk_data = await cursor.fetchall()

        if not afk_data:
            embed = discord.Embed(
                title="📋 АФК Панель",
                description="В АФК никого нет!",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Обновлено: {datetime.datetime.now().strftime('%H:%M:%S')}")
        else:
            table_lines = []
            table_lines.append("```")
            table_lines.append("╔═══════════════════════════════════════════════════════════════╗")
            table_lines.append("║              📋 СПИСОК ПОЛЬЗОВАТЕЛЕЙ В АФК                   ║")
            table_lines.append("╠═══════════════════════════════════════════════════════════════╣")
            
            for user_id, reason, afk_time, return_time in afk_data:
                try:
                    user = await bot.fetch_user(user_id)
                    user_name = user.name[:15]
                except:
                    user_name = "Unknown"

                dt_return = datetime.datetime.fromisoformat(return_time)
                now = datetime.datetime.now()
                remaining = dt_return - now

                if remaining.total_seconds() > 0:
                    hours = int(remaining.total_seconds() // 3600)
                    mins = int((remaining.total_seconds() % 3600) // 60)
                    time_left = f"{hours}ч {mins}м" if hours > 0 else f"{mins}м"
                else:
                    time_left = "Скоро вернётся"

                reason_short = reason[:25] if len(reason) <= 25 else reason[:22] + "..."
                
                table_lines.append(f"║ 👤 {user_name:<15} │ ⏱️ {time_left:<12} ║")
                table_lines.append(f"║    📝 {reason_short:<49} ║")
                table_lines.append("║───────────────────────────────────────────────────────────────║")

            table_lines.append("╚═══════════════════════════════════════════════════════════════╝")
            table_lines.append("```")

            embed = discord.Embed(
                title="📋 АФК Панель",
                description="\n".join(table_lines),
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"Обновлено: {datetime.datetime.now().strftime('%H:%M:%S')} | Всего в АФК: {len(afk_data)}")

        message = await interaction.followup.send(embed=embed)
        bot.afklist_message = message
        bot.afklist_channel = interaction.channel
    except Exception as e:
        await interaction.followup.send(
            f"Ошибка при создании АФК панели: {str(e)}",
            ephemeral=True
        )
        print(f"Ошибка в afklist: {e}")

# ---------- КОМАНДА /WARN ----------

@bot.tree.command(
    name="warn",
    description="Выдать варн пользователю",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.checks.has_permissions(administrator=True)
async def warn(interaction: discord.Interaction, user: discord.User, violation_type: str):
    try:
        if len(violation_type) > 200:
            await interaction.response.send_message(
                "Ошибка: тип нарушения слишком длинный (максимум 200 символов).",
                ephemeral=True,
                delete_after=180
            )
            return

        await bot.db.execute(
            "INSERT OR IGNORE INTO users (user_id, joined_at) VALUES (?, ?)",
            (user.id, datetime.datetime.now().isoformat())
        )

        now = datetime.datetime.now()
        await bot.db.execute(
            "INSERT INTO warns (user_id, admin_id, violation_type, timestamp) VALUES (?, ?, ?, ?)",
            (user.id, interaction.user.id, violation_type, now.isoformat())
        )
        await bot.db.commit()

        async with bot.db.execute(
            "SELECT id FROM warns WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user.id,)
        ) as cursor:
            warn_id = (await cursor.fetchone())[0]

        async with bot.db.execute(
            "SELECT COUNT(*) FROM warns WHERE user_id = ?",
            (user.id,)
        ) as cursor:
            warn_count = (await cursor.fetchone())[0]

        embed_admin = discord.Embed(
            title="⚠️ Варн выдан",
            color=discord.Color.red()
        )
        embed_admin.add_field(name="Игрок", value=user.mention, inline=True)
        embed_admin.add_field(name="ID варна", value=str(warn_id), inline=True)
        embed_admin.add_field(name="Тип нарушения", value=violation_type, inline=False)
        embed_admin.add_field(name="Всего варнов", value=f"{warn_count}/3", inline=True)
        embed_admin.add_field(name="Администратор", value=interaction.user.mention, inline=True)
        await interaction.response.send_message(embed=embed_admin)

        try:
            embed_user = discord.Embed(
                title="⚠️ Вам выдан варн",
                color=discord.Color.red()
            )
            embed_user.add_field(name="ID варна", value=str(warn_id), inline=True)
            embed_user.add_field(name="Тип нарушения", value=violation_type, inline=False)
            embed_user.add_field(name="Выдал администратор", value=interaction.user.name, inline=True)
            embed_user.add_field(name="Время", value=discord.utils.format_dt(now, style='F'), inline=False)
            embed_user.add_field(name="Всего варнов", value=f"{warn_count}/3", inline=False)
            embed_user.set_footer(text=f"Сервер: {interaction.guild.name}")
            await user.send(embed=embed_user)
        except discord.Forbidden:
            print(f"Не удалось отправить ЛС пользователю {user}")
    except Exception as e:
        await interaction.response.send_message(
            f"Ошибка при выдаче варна: {str(e)}",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в warn: {e}")

# ---------- КОМАНДА /WARNINFO ----------

@bot.tree.command(
    name="warninfo",
    description="Посмотреть варны пользователя",
    guild=discord.Object(id=GUILD_ID)
)
async def warninfo(interaction: discord.Interaction, user: discord.User = None):
    try:
        target = user or interaction.user

        async with bot.db.execute(
            "SELECT COUNT(*) FROM warns WHERE user_id = ?",
            (target.id,)
        ) as cursor:
            warn_count = (await cursor.fetchone())[0]

        async with bot.db.execute(
            "SELECT id, admin_id, violation_type, timestamp FROM warns WHERE user_id = ? ORDER BY id DESC",
            (target.id,)
        ) as cursor:
            warns = await cursor.fetchall()

        embed = discord.Embed(
            title=f"📋 Варны пользователя {target.display_name}",
            color=discord.Color.orange() if warn_count > 0 else discord.Color.green()
        )
        embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)
        embed.add_field(name="Всего варнов", value=f"{warn_count}/3", inline=False)

        if warns:
            warns_text = []
            for warn_id, admin_id, violation_type, timestamp in warns:
                dt = datetime.datetime.fromisoformat(timestamp)
                admin = interaction.guild.get_member(admin_id)
                admin_name = admin.display_name if admin else f"ID: {admin_id}"
                warns_text.append(
                    f"ID {warn_id} | {dt.strftime('%d.%m.%Y %H:%M')} | {admin_name}\n{violation_type}"
                )
            embed.add_field(name="История варнов", value="\n\n".join(warns_text), inline=False)
        else:
            embed.add_field(name="История варнов", value="Нет варнов", inline=False)

        embed.set_footer(text=f"ID пользователя: {target.id}")
        await interaction.response.send_message(embed=embed, ephemeral=False)
    except Exception as e:
        await interaction.response.send_message(
            f"Ошибка при получении информации о варнах: {str(e)}",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в warninfo: {e}")

# ---------- КОМАНДА /DWARN ----------

@bot.tree.command(
    name="dwarn",
    description="Удалить варн по ID",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.checks.has_permissions(administrator=True)
async def dwarn(interaction: discord.Interaction, warn_id: int):
    try:
        async with bot.db.execute(
            "SELECT user_id, violation_type, timestamp FROM warns WHERE id = ?",
            (warn_id,)
        ) as cursor:
            warn_info = await cursor.fetchone()

        if not warn_info:
            await interaction.response.send_message(
                f"Ошибка: варн с ID {warn_id} не найден.",
                ephemeral=True,
                delete_after=180
            )
            return

        user_id, violation_type, timestamp = warn_info
        await bot.db.execute(
            "DELETE FROM warns WHERE id = ?",
            (warn_id,)
        )
        await bot.db.commit()

        async with bot.db.execute(
            "SELECT COUNT(*) FROM warns WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            remaining_warns = (await cursor.fetchone())[0]

        try:
            user = await bot.fetch_user(user_id)
            user_mention = f"{user.mention} ({user.display_name})"
        except:
            user_mention = f"ID: {user_id}"

        embed = discord.Embed(
            title="✅ Варн удалён",
            color=discord.Color.green()
        )
        embed.add_field(name="ID варна", value=str(warn_id), inline=True)
        embed.add_field(name="Пользователь", value=user_mention, inline=True)
        embed.add_field(name="Тип нарушения", value=violation_type, inline=False)
        embed.add_field(name="Оставшиеся варны", value=str(remaining_warns), inline=False)
        await interaction.response.send_message(embed=embed)

        try:
            user = await bot.fetch_user(user_id)
            embed_user = discord.Embed(
                title="✅ Варн удалён",
                description=f"Администратор {interaction.user.name} удалил ваш варн ID {warn_id}",
                color=discord.Color.green()
            )
            embed_user.add_field(name="Тип нарушения", value=violation_type, inline=False)
            embed_user.add_field(name="Оставшиеся варны", value=f"{remaining_warns}/3", inline=False)
            await user.send(embed=embed_user)
        except discord.Forbidden:
            pass
    except Exception as e:
        await interaction.response.send_message(
            f"Ошибка при удалении варна: {str(e)}",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в dwarn: {e}")

# ---------- КОМАНДА /BAN ----------

@bot.tree.command(
    name="ban",
    description="Забанить пользователя",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, user: discord.User, reason: str = "Не указана"):
    try:
        if isinstance(user, discord.Member) and user.top_role >= interaction.user.top_role:
            await interaction.response.send_message(
                "Ошибка: вы не можете забанить пользователя с такой же или выше ролью.",
                ephemeral=True,
                delete_after=180
            )
            return

        await interaction.guild.ban(user, reason=reason)

        embed = discord.Embed(
            title="⛔ Бан",
            description=f"{user.mention} забанен.\nПричина: {reason}",
            color=discord.Color.red()
        )
        embed.add_field(name="Администратор", value=interaction.user.mention, inline=True)
        await interaction.response.send_message(embed=embed)

        try:
            await user.send(f"Вы были забанены на сервере {interaction.guild.name}.\nПричина: {reason}")
        except:
            pass
    except discord.Forbidden:
        await interaction.response.send_message(
            "Ошибка: у бота недостаточно прав для бана.",
            ephemeral=True,
            delete_after=180
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Ошибка при бане: {str(e)}",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в ban: {e}")

# ---------- КОМАНДА /UNBAN ----------

@bot.tree.command(
    name="unban",
    description="Разбанить пользователя по ID",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await interaction.guild.unban(user)

        embed = discord.Embed(
            title="✅ Разбан",
            description=f"Пользователь {user} разбанен.",
            color=discord.Color.green()
        )
        embed.add_field(name="Администратор", value=interaction.user.mention, inline=True)
        await interaction.response.send_message(embed=embed)
    except discord.NotFound:
        await interaction.response.send_message(
            "Ошибка: пользователь не найден или не забанен.",
            ephemeral=True,
            delete_after=180
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Ошибка при разбане: {str(e)}",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в unban: {e}")

# ---------- КОМАНДА /TIMEOUT ----------

@bot.tree.command(
    name="timeout",
    description="Выдать мут пользователю",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, user: discord.Member, minutes: int, reason: str = "Не указана"):
    try:
        if user.top_role >= interaction.user.top_role:
            await interaction.response.send_message(
                "Ошибка: вы не можете замутить пользователя с такой же или выше ролью.",
                ephemeral=True,
                delete_after=180
            )
            return

        if minutes <= 0 or minutes > 40320:
            await interaction.response.send_message(
                "Ошибка: укажите время от 1 до 40320 минут (28 дней).",
                ephemeral=True,
                delete_after=180
            )
            return

        duration = datetime.timedelta(minutes=minutes)
        until = datetime.datetime.now(datetime.timezone.utc) + duration

        await user.timeout(until, reason=reason)

        embed = discord.Embed(
            title="🔇 Мут выдан",
            description=f"{user.mention} получил мут на {minutes} минут.\nПричина: {reason}",
            color=discord.Color.orange()
        )
        embed.add_field(name="Администратор", value=interaction.user.mention, inline=True)
        await interaction.response.send_message(embed=embed)
    except discord.Forbidden:
        await interaction.response.send_message(
            "Ошибка: у бота недостаточно прав для мута.",
            ephemeral=True,
            delete_after=180
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Ошибка при выдаче мута: {str(e)}",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в timeout: {e}")

# ---------- КОМАНДА /UNTIMEOUT ----------

@bot.tree.command(
    name="untimeout",
    description="Снять мут с пользователя",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, user: discord.Member):
    try:
        if not user.is_timed_out():
            await interaction.response.send_message(
                f"Ошибка: {user.mention} не находится в муте.",
                ephemeral=True,
                delete_after=180
            )
            return

        await user.timeout(None)

        embed = discord.Embed(
            title="✅ Мут снят",
            description=f"С {user.mention} снят мут.",
            color=discord.Color.green()
        )
        embed.add_field(name="Администратор", value=interaction.user.mention, inline=True)
        await interaction.response.send_message(embed=embed)
    except discord.Forbidden:
        await interaction.response.send_message(
            "Ошибка: у бота недостаточно прав для снятия мута.",
            ephemeral=True,
            delete_after=180
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Ошибка при снятии мута: {str(e)}",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в untimeout: {e}")

# ---------- КОМАНДА /KICK ----------

@bot.tree.command(
    name="kick",
    description="Выгнать пользователя",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = "Не указана"):
    try:
        if user.top_role >= interaction.user.top_role:
            await interaction.response.send_message(
                "Ошибка: вы не можете выгнать пользователя с такой же или выше ролью.",
                ephemeral=True,
                delete_after=180
            )
            return

        await user.kick(reason=reason)

        embed = discord.Embed(
            title="👢 Кик",
            description=f"{user.mention} выгнан со сервера.\nПричина: {reason}",
            color=discord.Color.red()
        )
        embed.add_field(name="Администратор", value=interaction.user.mention, inline=True)
        await interaction.response.send_message(embed=embed)

        try:
            await user.send(f"Вы были выгнаны со сервера {interaction.guild.name}.\nПричина: {reason}")
        except:
            pass
    except discord.Forbidden:
        await interaction.response.send_message(
            "Ошибка: у бота недостаточно прав для кика.",
            ephemeral=True,
            delete_after=180
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Ошибка при кике: {str(e)}",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в kick: {e}")

# ---------- КОМАНДА /BROADCAST ----------

@bot.tree.command(
    name="broadcast",
    description="Отправить сообщение в канал несколько раз (только админы)",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.checks.has_permissions(administrator=True)
async def broadcast(interaction: discord.Interaction):
    try:
        await interaction.response.send_modal(BroadcastModal(bot))
    except Exception as e:
        await interaction.response.send_message(
            f"Ошибка при открытии формы broadcast: {str(e)}",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в broadcast: {e}")

# ---------- ОБРАБОТЧИК ОШИБОК КОМАНД ----------

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "Ошибка: у вас недостаточно прав для использования этой команды.",
            ephemeral=True,
            delete_after=180
        )
    elif isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"Команда на перезарядке. Попробуйте через {error.retry_after:.0f} секунд.",
            ephemeral=True,
            delete_after=180
        )
    else:
        await interaction.response.send_message(
            "Произошла непредвиденная ошибка.",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка команды: {error}")

if __name__ == "__main__":
    bot.run(TOKEN)
