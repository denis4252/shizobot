import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiosqlite
import datetime
import asyncio
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
AFK_PANEL_CHANNEL_ID = 1443454810589368320

if not TOKEN:
    raise ValueError("DISCORD_TOKEN не найден в .env файле!")

# ---------- МОДАЛЬНЫЕ ОКНА ----------

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

            now = datetime.datetime.now()
            return_time = now + datetime.timedelta(minutes=minutes)

            await self.bot_instance.db.execute(
                "INSERT OR REPLACE INTO afk_users (user_id, reason, afk_time, return_time) VALUES (?, ?, ?, ?)",
                (interaction.user.id, self.reason.value, now.isoformat(), return_time.isoformat())
            )
            await self.bot_instance.db.commit()

            msg = await interaction.response.send_message(
                f"✅ Твой АФК статус установлен на {minutes} минут.\n**Причина:** {self.reason.value}",
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
                    msg = await channel.send(self.message.value)
                    asyncio.create_task(self._delete_after(msg, 180))
                    if i < repeat - 1:
                        await asyncio.sleep(0.5)
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

    async def _delete_after(self, message, delay):
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except:
            pass

# ---------- БОТ И БД ----------

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.synced = False
        self.db = None
        self.afklist_message = None
        self.afklist_channel = None

    async def setup_hook(self):
        self.db = await aiosqlite.connect("SchizoBot.db")
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

        # Отправка сообщения с кнопками в фиксированный канал
        try:
            channel = self.get_channel(AFK_PANEL_CHANNEL_ID)
            if channel:
                # Удаляем старые сообщения бота
                deleted_count = 0
                async for msg in channel.history(limit=50):
                    if msg.author == self.user and deleted_count < 10:
                        try:
                            await msg.delete()
                            deleted_count += 1
                        except:
                            pass
                
                view = AfkControlView(self)
                await channel.send(
                    "📋 **Управление АФК**\n\nНажимай на кнопки ниже:",
                    view=view
                )
                print(f"Сообщение с AFK-кнопками отправлено в канал {AFK_PANEL_CHANNEL_ID}")
        except Exception as e:
            print(f"Ошибка при отправке сообщения с AFK-кнопками: {e}")

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
            table_lines.append("╔══════════════════════════════════════════════════════════════════╗")
            table_lines.append("║                    📋 СПИСОК АФК                                ║")
            table_lines.append("╠══════════════════════════════════════════════════════════════════╣")

            for user_id, reason, afk_time, return_time in afk_data:
                try:
                    guild = self.get_guild(AFK_GUILD_ID) or self.get_guild(GUILD_ID)
                    member = None
                    if guild:
                        member = guild.get_member(user_id)
                    
                    # Приоритет: display_name (ник на сервере), потом global_name, потом username
                    if member:
                        user_name = member.display_name[:18]
                    else:
                        user = await self.fetch_user(user_id)
                        user_name = (user.global_name or user.name)[:18]
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
                    time_left = "Скоро"

                reason_short = reason[:28] if len(reason) <= 28 else reason[:25] + "..."

                table_lines.append(f"║ 👤 {user_name:<18} │ ⏱️ {time_left:<8}                    ║")
                table_lines.append(f"║ 📝 Причина: {reason_short:<45} ║")
                table_lines.append("║" + "─" * 66 + "║")

            table_lines.append("╚══════════════════════════════════════════════════════════════════╝")
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

# ---------- VIEWS (КНОПКИ) ----------

class AfkControlView(discord.ui.View):
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot_instance = bot_instance

    @discord.ui.button(label="📋 АФК-лист", style=discord.ButtonStyle.primary, custom_id="open_afklist")
    async def open_afklist(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.user.guild_permissions.administrator:
                msg = await interaction.response.send_message(
                    "Эта кнопка только для администраторов.",
                    ephemeral=True,
                    delete_after=10
                )
                asyncio.create_task(bot._delete_after_custom(msg, 10))
                return

            await interaction.response.defer(ephemeral=True)

            embed = discord.Embed(
                title="📋 АФК Панель",
                description="Загрузка списка...",
                color=discord.Color.gold()
            )

            if self.bot_instance.afklist_message is None:
                msg = await interaction.channel.send(embed=embed)
                self.bot_instance.afklist_message = msg
                self.bot_instance.afklist_channel = interaction.channel
            else:
                await self.bot_instance.afklist_message.edit(embed=embed)

            await self.bot_instance.update_afk_panel()
            
            await interaction.followup.send("✅ АФК-лист обновлён!", ephemeral=True, delete_after=5)
        except Exception as e:
            await interaction.followup.send(
                f"Ошибка при открытии АФК панели: {str(e)}",
                ephemeral=True,
                delete_after=15
            )

    @discord.ui.button(label="😴 AFK", style=discord.ButtonStyle.secondary, custom_id="open_afk_modal")
    async def open_afk_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(AFKModal(self.bot_instance))
        except Exception as e:
            await interaction.response.send_message(
                f"Ошибка при открытии формы АФК: {str(e)}",
                ephemeral=True,
                delete_after=15
            )

class InfoView(discord.ui.View):
    def __init__(self, bot_instance, user):
        super().__init__(timeout=None)
        self.bot_instance = bot_instance
        self.user = user

    @discord.ui.button(label="📚 Справка", style=discord.ButtonStyle.primary, custom_id="info_help")
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            msg = await interaction.response.send_message("Эта кнопка не для тебя!", ephemeral=True, delete_after=5)
            asyncio.create_task(bot._delete_after_custom(msg, 5))
            return

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
        embed.set_footer(text="SchizoBot v3.0 | Показаны только доступные тебе команды")

        back_view = BackView()
        msg = await interaction.response.send_message(embed=embed, view=back_view, ephemeral=True)
        asyncio.create_task(bot._delete_after_custom(msg, 180))

    @discord.ui.button(label="🛑 Закрыть", style=discord.ButtonStyle.danger, custom_id="info_close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            msg = await interaction.response.send_message("Эта кнопка не для тебя!", ephemeral=True, delete_after=5)
            asyncio.create_task(bot._delete_after_custom(msg, 5))
            return
        await interaction.response.defer()
        await interaction.delete_original_response()

class BackView(discord.ui.View):
    @discord.ui.button(label="⬅️ Назад", style=discord.ButtonStyle.secondary, custom_id="back_to_info")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="SchizoBot",
            description="Привет, Ебланчик!\n\nЭто SchizoBot — разработан специально для SHIZORAGE FAMQ.\n\nДля продолжения определись, что тебе необходимо.",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else bot.user.default_avatar.url)
        embed.set_footer(text="SchizoBot v3.0 | 2025")
        view = InfoView(bot, interaction.user)
        await interaction.response.edit_message(embed=embed, view=view)

# ---------- ФУНКЦИЯ ДЛЯ УДАЛЕНИЯ СООБЩЕНИЙ ----------

async def _delete_after_custom(message, delay):
    """Удалить сообщение через delay секунд"""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass

bot._delete_after_custom = _delete_after_custom

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
        embed.set_footer(text="SchizoBot v3.0 | Показаны только доступные тебе команды")
        msg = await interaction.response.send_message(embed=embed, ephemeral=True, delete_after=180)
        asyncio.create_task(bot._delete_after_custom(msg, 180))
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
            title="SchizoBot",
            description="Привет, ебланчик!\n\nЭто SchizoBot — разработан специально для SHIZORAGE FAMQ.\n\nДля продолжения определись, что тебе необходимо.",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else bot.user.default_avatar.url)
        embed.set_footer(text="SchizoBot v3.0 | 2025")
        view = InfoView(bot, interaction.user)
        msg = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    except Exception as e:
        msg = await interaction.response.send_message(
            "Ошибка при загрузке информации.",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в info: {e}")

# ---------- КОМАНДА /AFK ----------

@bot.tree.command(
    name="afk",
    description="Установить статус АФК с причиной",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.describe(
    reason="Причина АФК (например: работа, учёба)",
    minutes="Сколько минут будешь в АФК? (1-1440)"
)
async def afk(interaction: discord.Interaction, reason: str = None, minutes: int = None):
    try:
        if reason is None or minutes is None:
            await interaction.response.send_modal(AFKModal(bot))
            return

        if minutes <= 0 or minutes > 1440:
            msg = await interaction.response.send_message(
                "Ошибка: укажите время от 1 до 1440 минут (24 часа).",
                ephemeral=True,
                delete_after=180
            )
            asyncio.create_task(bot._delete_after_custom(msg, 180))
            return

        now = datetime.datetime.now()
        return_time = now + datetime.timedelta(minutes=minutes)

        await bot.db.execute(
            "INSERT OR REPLACE INTO afk_users (user_id, reason, afk_time, return_time) VALUES (?, ?, ?, ?)",
            (interaction.user.id, reason, now.isoformat(), return_time.isoformat())
        )
        await bot.db.commit()

        msg = await interaction.response.send_message(
            f"✅ Твой АФК статус установлен на {minutes} минут.\n**Причина:** {reason}",
            ephemeral=True,
            delete_after=180
        )
        asyncio.create_task(bot._delete_after_custom(msg, 180))

    except Exception as e:
        msg = await interaction.response.send_message(
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
            msg = await interaction.response.send_message(
                "Ты не находишься в АФК списке.",
                ephemeral=True,
                delete_after=180
            )
            asyncio.create_task(bot._delete_after_custom(msg, 180))
            return

        await bot.db.execute(
            "DELETE FROM afk_users WHERE user_id = ?",
            (interaction.user.id,)
        )
        await bot.db.commit()

        msg = await interaction.response.send_message(
            "✅ Ты убран из АФК списка.",
            ephemeral=True,
            delete_after=180
        )
        asyncio.create_task(bot._delete_after_custom(msg, 180))

    except Exception as e:
        msg = await interaction.response.send_message(
            f"Ошибка при удалении из АФК: {str(e)}",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в unafk: {e}")

# ---------- КОМАНДА /AFKLIST ----------

@bot.tree.command(
    name="afklist",
    description="Список пользователей в АФК (обновляется каждую минуту)",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.checks.has_permissions(administrator=True)
async def afklist(interaction: discord.Interaction):
    try:
        if bot.afklist_message is not None:
            msg = await interaction.response.send_message(
                "⚠️ АФК панель уже создана! Используй её же для обновлений.",
                ephemeral=True,
                delete_after=180
            )
            asyncio.create_task(bot._delete_after_custom(msg, 180))
            return

        await interaction.response.defer()

        embed = discord.Embed(
            title="📋 АФК Панель",
            description="Загрузка списка...",
            color=discord.Color.gold()
        )

        message = await interaction.followup.send(embed=embed)
        bot.afklist_message = message
        bot.afklist_channel = interaction.channel

        await bot.update_afk_panel()

    except Exception as e:
        msg = await interaction.followup.send(
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
@app_commands.describe(
    user="Пользователь для выдачи варна",
    reason="Причина варна"
)
async def warn(interaction: discord.Interaction, user: discord.User, reason: str = "Не указана"):
    try:
        if len(reason) > 200:
            msg = await interaction.response.send_message(
                "Ошибка: причина слишком длинная (максимум 200 символов).",
                ephemeral=True,
                delete_after=180
            )
            asyncio.create_task(bot._delete_after_custom(msg, 180))
            return

        now = datetime.datetime.now()
        await bot.db.execute(
            "INSERT INTO warns (user_id, admin_id, violation_type, timestamp) VALUES (?, ?, ?, ?)",
            (user.id, interaction.user.id, reason, now.isoformat())
        )
        await bot.db.commit()

        async with bot.db.execute("SELECT COUNT(*) FROM warns WHERE user_id = ?", (user.id,)) as cursor:
            warn_count = (await cursor.fetchone())[0]

        embed = discord.Embed(
            title="⚠️ Варн выдан",
            description=f"{user.mention} получил варн за: {reason}",
            color=discord.Color.red()
        )
        embed.add_field(name="Администратор", value=interaction.user.mention, inline=True)
        embed.add_field(name="Всего варнов", value=f"{warn_count}/3", inline=True)
        embed.set_footer(text="SchizoBot v3.0")

        msg = await interaction.response.send_message(embed=embed, delete_after=180)
        asyncio.create_task(bot._delete_after_custom(msg, 180))

    except Exception as e:
        msg = await interaction.response.send_message(
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
@app_commands.describe(user="Пользователь (по умолчанию вы)")
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
            title=f"📋 Варны пользователя {target.name}",
            color=discord.Color.orange() if warn_count > 0 else discord.Color.green()
        )
        embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)
        embed.add_field(name="Всего варнов", value=f"{warn_count}/3", inline=False)

        if warns:
            warns_text = []
            for warn_id, admin_id, violation_type, timestamp in warns:
                dt = datetime.datetime.fromisoformat(timestamp)
                try:
                    admin = await bot.fetch_user(admin_id)
                    admin_name = admin.name
                except:
                    admin_name = f"ID: {admin_id}"
                warns_text.append(
                    f"**ID {warn_id}** | {dt.strftime('%d.%m.%Y %H:%M')} | {admin_name}\n{violation_type}"
                )
            embed.add_field(name="История варнов", value="\n\n".join(warns_text), inline=False)
        else:
            embed.add_field(name="История варнов", value="Нет варнов ✅", inline=False)

        embed.set_footer(text=f"ID пользователя: {target.id}")

        msg = await interaction.response.send_message(embed=embed, ephemeral=False, delete_after=180)
        asyncio.create_task(bot._delete_after_custom(msg, 180))

    except Exception as e:
        msg = await interaction.response.send_message(
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
@app_commands.describe(warn_id="ID варна для удаления")
async def dwarn(interaction: discord.Interaction, warn_id: int):
    try:
        async with bot.db.execute(
            "SELECT user_id, violation_type, timestamp FROM warns WHERE id = ?",
            (warn_id,)
        ) as cursor:
            warn_info = await cursor.fetchone()

        if not warn_info:
            msg = await interaction.response.send_message(
                f"Ошибка: варн с ID {warn_id} не найден.",
                ephemeral=True,
                delete_after=180
            )
            asyncio.create_task(bot._delete_after_custom(msg, 180))
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
            user_mention = f"{user.mention} ({user.name})"
        except:
            user_mention = f"ID: {user_id}"

        embed = discord.Embed(
            title="✅ Варн удалён",
            color=discord.Color.green()
        )
        embed.add_field(name="ID варна", value=str(warn_id), inline=True)
        embed.add_field(name="Пользователь", value=user_mention, inline=True)
        embed.add_field(name="Тип нарушения", value=violation_type, inline=False)
        embed.add_field(name="Оставшиеся варны", value=f"{remaining_warns}/3", inline=False)

        msg = await interaction.response.send_message(embed=embed, delete_after=180)
        asyncio.create_task(bot._delete_after_custom(msg, 180))

    except Exception as e:
        msg = await interaction.response.send_message(
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
@app_commands.describe(
    user="Пользователь для бана",
    reason="Причина бана"
)
async def ban(interaction: discord.Interaction, user: discord.User, reason: str = "Не указана"):
    try:
        if isinstance(user, discord.Member) and user.top_role >= interaction.user.top_role:
            msg = await interaction.response.send_message(
                "Ошибка: вы не можете забанить пользователя с такой же или выше ролью.",
                ephemeral=True,
                delete_after=180
            )
            asyncio.create_task(bot._delete_after_custom(msg, 180))
            return

        await interaction.guild.ban(user, reason=reason)

        embed = discord.Embed(
            title="⛔ Бан",
            description=f"{user.mention} забанен.\nПричина: {reason}",
            color=discord.Color.red()
        )
        embed.add_field(name="Администратор", value=interaction.user.mention, inline=True)

        msg = await interaction.response.send_message(embed=embed, delete_after=180)
        asyncio.create_task(bot._delete_after_custom(msg, 180))

        try:
            await user.send(f"Вы были забанены на сервере {interaction.guild.name}.\nПричина: {reason}")
        except:
            pass

    except discord.Forbidden:
        msg = await interaction.response.send_message(
            "Ошибка: у бота недостаточно прав для бана.",
            ephemeral=True,
            delete_after=180
        )
        asyncio.create_task(bot._delete_after_custom(msg, 180))
    except Exception as e:
        msg = await interaction.response.send_message(
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
@app_commands.describe(user_id="ID пользователя для разбана")
async def unban(interaction: discord.Interaction, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await interaction.guild.unban(user)

        embed = discord.Embed(
            title="✅ Разбан",
            description=f"Пользователь {user.mention} разбанен.",
            color=discord.Color.green()
        )
        embed.add_field(name="Администратор", value=interaction.user.mention, inline=True)

        msg = await interaction.response.send_message(embed=embed, delete_after=180)
        asyncio.create_task(bot._delete_after_custom(msg, 180))

    except discord.NotFound:
        msg = await interaction.response.send_message(
            "Ошибка: пользователь не найден или не забанен.",
            ephemeral=True,
            delete_after=180
        )
        asyncio.create_task(bot._delete_after_custom(msg, 180))
    except Exception as e:
        msg = await interaction.response.send_message(
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
@app_commands.describe(
    user="Пользователь",
    minutes="Длительность мута в минутах (1-40320)",
    reason="Причина мута"
)
async def timeout(interaction: discord.Interaction, user: discord.Member, minutes: int, reason: str = "Не указана"):
    try:
        if user.top_role >= interaction.user.top_role:
            msg = await interaction.response.send_message(
                "Ошибка: вы не можете замутить пользователя с такой же или выше ролью.",
                ephemeral=True,
                delete_after=180
            )
            asyncio.create_task(bot._delete_after_custom(msg, 180))
            return

        if minutes <= 0 or minutes > 40320:
            msg = await interaction.response.send_message(
                "Ошибка: укажите время от 1 до 40320 минут (28 дней).",
                ephemeral=True,
                delete_after=180
            )
            asyncio.create_task(bot._delete_after_custom(msg, 180))
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

        msg = await interaction.response.send_message(embed=embed, delete_after=180)
        asyncio.create_task(bot._delete_after_custom(msg, 180))

    except discord.Forbidden:
        msg = await interaction.response.send_message(
            "Ошибка: у бота недостаточно прав для мута.",
            ephemeral=True,
            delete_after=180
        )
        asyncio.create_task(bot._delete_after_custom(msg, 180))
    except Exception as e:
        msg = await interaction.response.send_message(
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
            msg = await interaction.response.send_message(
                f"Ошибка: {user.mention} не находится в муте.",
                ephemeral=True,
                delete_after=180
            )
            asyncio.create_task(bot._delete_after_custom(msg, 180))
            return

        await user.timeout(None)

        embed = discord.Embed(
            title="✅ Мут снят",
            description=f"С {user.mention} снят мут.",
            color=discord.Color.green()
        )
        embed.add_field(name="Администратор", value=interaction.user.mention, inline=True)

        msg = await interaction.response.send_message(embed=embed, delete_after=180)
        asyncio.create_task(bot._delete_after_custom(msg, 180))

    except discord.Forbidden:
        msg = await interaction.response.send_message(
            "Ошибка: у бота недостаточно прав для снятия мута.",
            ephemeral=True,
            delete_after=180
        )
        asyncio.create_task(bot._delete_after_custom(msg, 180))
    except Exception as e:
        msg = await interaction.response.send_message(
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
@app_commands.describe(
    user="Пользователь",
    reason="Причина кика"
)
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = "Не указана"):
    try:
        if user.top_role >= interaction.user.top_role:
            msg = await interaction.response.send_message(
                "Ошибка: вы не можете выгнать пользователя с такой же или выше ролью.",
                ephemeral=True,
                delete_after=180
            )
            asyncio.create_task(bot._delete_after_custom(msg, 180))
            return

        await user.kick(reason=reason)

        embed = discord.Embed(
            title="👢 Кик",
            description=f"{user.mention} выгнан со сервера.\nПричина: {reason}",
            color=discord.Color.red()
        )
        embed.add_field(name="Администратор", value=interaction.user.mention, inline=True)

        msg = await interaction.response.send_message(embed=embed, delete_after=180)
        asyncio.create_task(bot._delete_after_custom(msg, 180))

        try:
            await user.send(f"Вы были выгнаны со сервера {interaction.guild.name}.\nПричина: {reason}")
        except:
            pass

    except discord.Forbidden:
        msg = await interaction.response.send_message(
            "Ошибка: у бота недостаточно прав для кика.",
            ephemeral=True,
            delete_after=180
        )
        asyncio.create_task(bot._delete_after_custom(msg, 180))
    except Exception as e:
        msg = await interaction.response.send_message(
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
        msg = await interaction.response.send_message(
            f"Ошибка при открытии формы broadcast: {str(e)}",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка в broadcast: {e}")

# ---------- ОБРАБОТЧИК ОШИБОК КОМАНД ----------

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = await interaction.response.send_message(
            "Ошибка: у вас недостаточно прав для использования этой команды.",
            ephemeral=True,
            delete_after=180
        )
        asyncio.create_task(bot._delete_after_custom(msg, 180))
    elif isinstance(error, app_commands.CommandOnCooldown):
        msg = await interaction.response.send_message(
            f"Команда на перезарядке. Попробуйте через {error.retry_after:.0f} секунд.",
            ephemeral=True,
            delete_after=180
        )
        asyncio.create_task(bot._delete_after_custom(msg, 180))
    else:
        msg = await interaction.response.send_message(
            "Произошла непредвиденная ошибка.",
            ephemeral=True,
            delete_after=180
        )
        print(f"Ошибка команды: {error}")

if __name__ == "__main__":
    bot.run(TOKEN)
