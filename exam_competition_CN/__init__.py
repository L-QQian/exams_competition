from otree.api import *
import json
import math
import datetime
import random
from shared_data import pool_manager  # 导入数字池模块
from shared_data import get_unique_numbers
import colorama
from colorama import Fore, Style
colorama.init(autoreset=True)







doc = """
Exam_competition(CN)    前半世界收入差大/后半世界收入差小  收入差大的世界抽奖
"""






class C(BaseConstants):
    NAME_IN_URL = 'exam_competition_CN'
    PLAYERS_PER_GROUP = 4
    NUM_ROUNDS = 10
    # 5期のみ
    INITIAL_POINTS = 0   
    # 初期保有額0ポイント
    ROUND_ALLOWANCE = 140  # 每轮给予140点，数值可以改，目的是为了不要成为负数。
    #希望不额外学习的人可以得到两次抽奖机会，我的设想是有一次重新考取名校的机会，一次找工作的机会。努力过失败了的人只有一次找工作的机会。考上名校的人比普通人多3次找工作的机会，因此是5次机会（设想）
    EFFORT_OPTIONS = [1,2,3,4,5, 6,7, 8,9, 10,11]    #選択時間の範囲

    # 努力時間によりコスト
    # 1時間は10、2時間から２ポイントずつ逓増しにいく（cost(h)=10h+(h^2−h)=h^2+9h ( h^2是2的平方)）
    A_LINEAR = 10   # 线性基准（越大整体越高）（成本变化基准，第一个小时学校习成本花费10点）
    LOTTERY_UNIT = 100 # 抽選ルール


class Subsession(BaseSubsession):
    def creating_session(self):
        if self.round_number == 1: #最初のラウンドでのみ数字のプールを初期化する（共有されるが重複しない）
            pool_manager.initialize_pool() #数字のプールを初期化する

            # #最初のラウンドのみ、初期人生ポイントと合計時間を初期化します。
            for p in self.get_players():
                p.participant.vars["points"] = C.INITIAL_POINTS  # 現在残るポイント
                p.participant.vars["total_points_for_lottery"] = 0
                p.participant.vars["first_half_points"] = 0
                p.participant.vars["second_half_points"] = 0
                p.participant.vars["first_half_hours"] = 0
                p.participant.vars["second_half_hours"] = 0
                p.participant.vars["phase"] = "first"  # フェー


class Group(BaseGroup):
    # FUNCTIONS
    def calculate_cost(self, effort: int) -> int:
        """本ラウンドの学習時間だけコストを計算する"""
        # コスト関数：
        #   cost(h) = h**2 + h + (C.A_LINEAR - 2)  C.A_LINEAR是常量里定义了的线性基准  A_LINEAR = 10   所以是cost(h) = h**2 + h + 8
        #   第1時間のコスト ≒ 10 （以後は限界コストが毎時間+2ずつ増加）
        # 轻微弯曲强度（越小越接近直线；从第2小时起每小时边际+ b）
        # パラメータを変更することで、全体のコスト曲線を簡単に調整できる。
        h = max(0, effort)
        if h == 0:
            return 0  # 将来允许“0小时学习”，那么学习成本为0（不花费人生点数）。
        #  例: A_LINEAR=10, B_CURVE=2.0 → 近似的に cost(1)=10, cost(2)=14, cost(3)=20,... 
        base = C.A_LINEAR - 2  # 原点調整   轻微弯曲强度（越小越接近直线；从第2小时起每小时边际+ b）
        cost = base + h**2 + h   # C.B_CURVE 是控制成本增长速度的曲线，C是成本。
        return int(cost)
        
    # ---- 回合结算（更新点数、统计学习时间、计算排名）----
    def set_rewards(self):
        players = self.get_players()

        for p in players:   # 上一回合结束时的余额（初始为0）
            # ✅ 防止刷新后 effort 为空导致错误计算
            if p.effort is None:
                print(f"⚠️ Warning: Player {p.id_in_group} has no effort data in round {self.round_number}. Skipping cost calculation.")
                continue
            
            base = p.participant.vars.get("points", C.INITIAL_POINTS)     # 当前剩余的人生点数（资源）
            base += C.ROUND_ALLOWANCE # 本回合发放的基础点数 (ROUND_ALLOWANCE = 140)
            # 根据本回合的学习时间计算成本
            cost = self.calculate_cost(p.effort)
            # 调试输出信息（后台可以看见函数和玩家的选择时长的对应成本）
            new_points = base - cost  # 扣除学习成本后的新点数
            p.points = int(new_points)  # 更新点数

            # 按阶段分开管理学习时间（前半/后半），排名仅在同阶段内比较
            if self.round_number <= 5:
                stage_hours = p.participant.vars.get("first_half_hours", 0) + p.effort
                p.participant.vars["first_half_hours"] = stage_hours
                p.total_hours = stage_hours  # 前半阶段的累计时间
            else:
                stage_hours = p.participant.vars.get("second_half_hours", 0) + p.effort
                p.participant.vars["second_half_hours"] = stage_hours
                p.total_hours = stage_hours  # 后半阶段的累计时间
            # 更新保存到 participant 变量
            p.participant.vars["points"] = p.points
            # ✅ 输出到后台日志
            exp_id = p.field_maybe_none("custom_id") or p.participant.vars.get("custom_id") or "未输入"
            print(f"→ 第 {p.round_number} 回合：扣除成本后得分为 {p.points} 分")
            print(f"Player {p.id_in_group}（实验编号: {exp_id}） | 学习时间: {p.effort} | 累计时间: {p.total_hours} | 成本: {cost} | 当前点数: {p.points}")



        # ---- 按阶段计算学力排名（基于累计学习时间）----
        ranked = sorted(players, key=lambda p: (-p.total_hours, p.id_in_group))
        current_rank = 1
        prev_hours_val = None
        for idx, p in enumerate(ranked):
            if idx == 0:
                p.round_rank = current_rank  
            else:
                # 如果当前玩家学习时间严格低于上一位，则名次+1（并列不变）
                if prev_hours_val is not None and p.total_hours < prev_hours_val:
                    current_rank += 1
                p.round_rank = current_rank
            prev_hours_val = p.total_hours    #次の反復での比較のために、前のプレイヤーの努力値を更新する    
            
         
    # ---- 合否判定（第5・第10ラウンドで呼ばれる）----
    def determine_final_winner(self):
        players = self.get_players()
   
         # 学力（累積時間）→ 同数なら残りポイント → さらに同数ならサイコロ
        sorted_players = sorted(
            players,
            key=lambda x: (-x.total_hours, -x.points, x.id_in_group)
        )
        # ランキング（同じ順位できる）
        current_rank = 1
        prev_hours = None
        prev_points = None

        for idx, p in enumerate(sorted_players):
            # 1番名はランキング1位
            if idx == 0:
                prev_hours = p.total_hours
                prev_points = p.points
                p.rank = current_rank
            else:
                # 如果与前一个玩家时间和点数完全相同，则并列排名
                if p.total_hours == prev_hours and p.points == prev_points:
                    p.rank = current_rank
                else:
                    current_rank = idx + 1  # ランキング（递增）
                    p.rank = current_rank
                    prev_hours = p.total_hours
                    prev_points = p.points
        # 合格者を判明する（1位（累積時間最大）候補
        max_hours = max(p.total_hours for p in players)
        finalists = [p for p in players if p.total_hours == max_hours]
        
        # 複数の人が1位になった場合は、残りのポイントを比較します
        if len(finalists) > 1:
            max_points = max(p.points for p in finalists)
            print(f"Max points among finalists: {max_points}")
            finalists = [p for p in finalists if p.points == max_points]
            print(f"⚡ Multiple finalists found. Proceeding to dice roll tie-breaker...")
            while True:
                rolls = {p: random.randint(1, 6) for p in finalists}
                for p, roll in rolls.items():
                    print(f"Player {p.id_in_group} rolled {roll}")

                max_roll = max(rolls.values())
                finalists = [p for p, roll in rolls.items() if roll == max_roll]

                if len(finalists) == 1:
                    break
                else:
                    print(f"⚡ Tie in dice rolls, re-rolling...")
        #合格者は一人だけ
        winner = finalists[0]

       # 段階別の追加報酬
        is_first_half = self.round_number <= 5  # 前5ラウンドまで
        if is_first_half:
            winner_bonus = 2400  # 一流大学に入った人への追加報酬
            loser_bonus = 300    # その他の人への追加報酬
        else:# 后5轮 → 收入差小
            winner_bonus = 900  # 一流大学に入った人への追加報酬
            loser_bonus = 800  

        # 付与 & 抽選用ポイント集計
        for p in players:
            p.winner = (p == winner)
            bonus = winner_bonus if p.winner else loser_bonus
            # p.final_points = p.points + bonus

            # 🟩 统一保存实验编号（避免“未输入”）
            exp_id = (
                getattr(p.participant, "label", None)
                or p.participant.vars.get("custom_id")
                or p.field_maybe_none("custom_id")
                or "未输入"
            )
            p.participant.vars["custom_id"] = exp_id  # 统一保存

            # フェーズ別の抽選用ポイント（ボーナス込み）を保持（ 前后半段的点数分开保存，方便抽奖合计
            if is_first_half:   # 🟩第5轮：使用“最后余额 + 奖励”作为前半积分
                last_round_points = p.in_round(5).points
                first_half_points = last_round_points + bonus
                p.participant.vars['first_half_points'] = first_half_points




                # 🟩 计算抽奖次数（每100点 = 1次）
                first_half_draws = math.floor(first_half_points / 100)  # ✅ 每100点1次抽奖
                p.participant.vars['first_half_draws'] = first_half_draws

                # ✅ 生成抽奖号码
                if first_half_draws > 0:
                    first_numbers = get_unique_numbers(first_half_draws)
                else:
                    first_numbers = []
                p.participant.vars['first_half_numbers'] = first_numbers

                # ✅立即保存抽奖号码到数据库
                p.final_points = first_half_points     # 确保最终点数也保存
                p.lottery_numbers_json = json.dumps(first_numbers)  # 保存抽奖号码到数据库




                # ✅ 保存前半累计学习时间
                total_first_hours = sum([p.in_round(r).effort for r in range(1, 6)])
                p.participant.vars['first_half_hours'] = total_first_hours
                
                # 打印日志
                print(f"[第5轮数据保存] Player {p.id_in_group}: 最终点数={first_half_points}")


            else:
                # 🟨后半世界：只记录积分，不抽奖
                last_round_points = p.in_round(10).points
                second_half_points = last_round_points + bonus
                p.participant.vars['second_half_points'] = second_half_points
                p.final_points = second_half_points  # ✅  保存到数据库字段

                
            # 🟩 总积分仅用于显示，不参与实际计算
            total_points = (
                p.participant.vars.get("first_half_points", 0)
                + p.participant.vars.get("second_half_points", 0)
            )
                
            p.participant.vars["total_points_for_lottery"] = total_points
           

        # ===== 🌏 前半（第5回合结束）总结 =====
        if self.round_number == 5 and self.id_in_subsession == 1:
            # 🟢 避免重复打印：若本session已输出过前半总结，则跳过
            if self.session.vars.get("logged_first_half"):
                return

            # --- 从第一个玩家 custom_id 提取组名（支持大小写、前后缀）---
            sample_id = players[0].field_maybe_none("custom_id") or ""
            # 🔧変更済：自動判定（プレイヤーの実験番号プレフィックスから組名を推定）
            group_label = ""
            initials = []
            for p in players:
                # ✅ 优先从 participant.vars 取 custom_id（更稳）
                cid = (
                    p.participant.vars.get("custom_id")
                    or p.field_maybe_none("custom_id")
                    or getattr(p.participant, "label", "")
                    or ""
                )
                if len(cid) >= 1 and cid[0].isalpha():
                    initials.append(cid[0])

            if initials:
                from collections import Counter
                counter = Counter(initials)
                most_common_initial, count = counter.most_common(1)[0]
                if count >= 2:
                    group_label = most_common_initial + "组"
                else:
                    group_label = initials[0] + "组"
            else:
                group_label = f"{self.id_in_subsession}组"

            # 🌟 新增：时间戳与视觉分隔线
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print("\n" + Fore.WHITE + "=" * 90 + Style.RESET_ALL)
            print(Fore.CYAN + f"[{timestamp}] 🌏 【{group_label}】前半（差距较大的世界）总结" + Style.RESET_ALL)
            print(Fore.WHITE + "=" * 90 + Style.RESET_ALL)

            for p in players:
                exp_id = p.participant.vars.get("custom_id") or p.field_maybe_none("custom_id") or "未输入"
                label = f"Player {p.id_in_group}"

                status = Fore.GREEN + "✅ 合格" if p.winner else Fore.RED + "❌ 不合格"

                print(f"\n{Fore.YELLOW}👤 {label}（实验编号: {exp_id}） {status}{Style.RESET_ALL}")

                cumulative_hours = 0
                for r in range(1, 6):  # 前半世界：第1～5回合
                    rp = p.in_round(r)
                    effort = rp.field_maybe_none('effort') or 0
                    points = rp.field_maybe_none('points') or 0
                    cumulative_hours += effort
                    cost = self.calculate_cost(effort)
                    print(f"  Round {r}: 努力 {effort} | 累计时间 {cumulative_hours} | 成本 {cost} | 点数 {points}")

                first_points = p.participant.vars.get("first_half_points", 0)
                draws = p.participant.vars.get("first_half_draws", 0)
                nums = p.participant.vars.get("first_half_numbers", [])
                print(f"  🎟️ 抽奖次数: {draws} 次 | 抽奖号码: {Fore.MAGENTA}{nums if nums else '（无）'}{Style.RESET_ALL}")
                print(f"  💰 前半世界的最终人生点数: {Fore.CYAN}{first_points} pt{Style.RESET_ALL}")


            print(Fore.CYAN + "=" * 90 + Style.RESET_ALL + "\n")
            # 🟢 标记前半日志已打印
            self.session.vars["logged_first_half"] = True

                # ===== 🌍 后半（第10回合结束）总结 =====
        elif self.round_number == 10 and self.id_in_subsession == 1:
            # 🟣 避免重复打印：若本session已输出过后半总结，则跳过
            if self.session.vars.get("logged_second_half"):
                return
            # --- 从第一个玩家 custom_id 提取组名（支持大小写、前后缀）---
            sample_id = players[0].field_maybe_none("custom_id") or ""
            # 🔧変更済：自動判定（プレイヤーの実験番号プレフィックスから組名を推定）
            group_label = ""
            initials = []
            for p in players:
                # ✅ 优先从 participant.vars 取 custom_id（更稳）
                cid = (
                    p.participant.vars.get("custom_id")
                    or p.field_maybe_none("custom_id")
                    or getattr(p.participant, "label", "")
                    or ""
                )
                if len(cid) >= 1 and cid[0].isalpha():
                    initials.append(cid[0])

            if initials:
                from collections import Counter
                counter = Counter(initials)
                most_common_initial, count = counter.most_common(1)[0]
                if count >= 2:
                    group_label = most_common_initial + "组"
                else:
                    group_label = initials[0] + "组"
            else:
                group_label = f"{self.id_in_subsession}组"

            # 🌟 新增：时间戳与视觉分隔线
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print("\n" + Fore.WHITE + "=" * 90 + Style.RESET_ALL)
            print(Fore.MAGENTA + f"[{timestamp}] 🌍 【{group_label}】后半（差距较小的世界）总结" + Style.RESET_ALL)
            print(Fore.WHITE + "=" * 90 + Style.RESET_ALL)

            for p in players:
                exp_id = p.participant.vars.get("custom_id") or p.field_maybe_none("custom_id") or "未输入"
                label = f"Player {p.id_in_group}"

                status = Fore.GREEN + "✅ 合格" if p.winner else Fore.RED + "❌ 不合格"

                print(f"\n{Fore.YELLOW}👤 {label}（实验编号: {exp_id}） {status}{Style.RESET_ALL}")

                cumulative_hours = 0
                for r in range(6, 11):  # 后半世界：第6～10回合
                    rp = p.in_round(r)
                    effort = rp.field_maybe_none('effort') or 0
                    points = rp.field_maybe_none('points') or 0
                    cumulative_hours += effort
                    cost = self.calculate_cost(effort)
                    print(f"  Round {r-5}: 努力 {effort} | 累计时间 {cumulative_hours} | 成本 {cost} | 点数 {points}")

                # ✅ 保留人生点数
                second_points = p.participant.vars.get("second_half_points", 0)
                print(f"  💰 后半世界的最终人生点数: {Fore.MAGENTA}{second_points} pt{Style.RESET_ALL}")
                
            print(Fore.MAGENTA + "=" * 90 + Style.RESET_ALL + "\n")
            # 🟣 标记后半日志已打印
            self.session.vars["logged_second_half"] = True


class Player(BasePlayer):
    consent = models.BooleanField(label='我同意参加本次研究')
    custom_id = models.StringField(label="请输入你的编号（例：AP1）")
    effort = models.IntegerField(choices=C.EFFORT_OPTIONS, label="这次你学习多少小时？")
    points = models.IntegerField(initial=C.INITIAL_POINTS)     # 当前剩余的人生点数（资源点数）
    final_points = models.IntegerField(initial=0)  # 加上奖励后的最终人生点数
    total_hours = models.IntegerField(initial=0)
    winner = models.BooleanField(initial=False)
    round_rank = models.IntegerField(initial=0) # 各回合的学力排名
    rank = models.IntegerField(initial=0)        # 最终的学力排名
    lottery_numbers_json = models.LongStringField(initial='[]')     # ✅ 保存抽到的号码（JSON 字符串）
    did_draw = models.BooleanField(initial=False)  # 是否已经抽过号（防止刷新重复抽）

    # ✅ 确认题（Q1〜Q6为True/False, Q7为数字输入）
    # ✅ 前六题：单选（True=正确，False=错误）
    q1 = models.BooleanField(choices=[[True, '正确'], [False, '错误']], widget=widgets.RadioSelectHorizontal)
    q2 = models.BooleanField(choices=[[True, '正确'], [False, '错误']], widget=widgets.RadioSelectHorizontal)
    q3 = models.BooleanField(choices=[[True, '正确'], [False, '错误']], widget=widgets.RadioSelectHorizontal)
    q4 = models.BooleanField(choices=[[True, '正确'], [False, '错误']], widget=widgets.RadioSelectHorizontal)
    q5 = models.BooleanField(choices=[[True, '正确'], [False, '错误']], widget=widgets.RadioSelectHorizontal)
    q6 = models.BooleanField(choices=[[True, '正确'], [False, '错误']], widget=widgets.RadioSelectHorizontal)

    # ✅ 第七题：数字输入（范围 1〜30）
    q7 = models.IntegerField(min=0, max=30)

# PAGES
class ConsentForm(Page):
    form_model = 'player'
    form_fields = ['consent']

    @staticmethod
    def is_displayed(player):  # 只在第1轮显示
        return player.round_number == 1

    @staticmethod
    def error_message(player: Player, values):
        if not values.get('consent'):
            return '未勾选无法进入下一页'  # 未勾选不能继续



# ✅ 確認問題ページ
class QuizCheck(Page):
    template_name = 'exam_competition_CN/QuizCheck.html'
    form_model = 'player'
    form_fields = ['q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7']

    @staticmethod
    def is_displayed(player):
        return player.round_number == 1  # 只在第1轮显示

    @staticmethod
    def error_message(player: Player, values):
        # 正确答案
        answers = dict(q1=True, q2=True, q3=False, q4=True, q5=False, q6=False,q7=15)
        explanations = {} 
        has_error = False   # ✅ 改动2：记录是否有错误

        for key, correct in answers.items():
            if values.get(key) != correct:
                has_error = True   # ✅ 标记存在错误

                if key == 'q1':
                    explanations[key] = "每一轮开始时你获得的人生积分用于学习的话会消耗你的人生积分。"
                elif key == 'q2':
                    explanations[key] = "学习时间越长高学习成绩越高，但是人生积分会减少。"
                elif key == 'q3':
                    explanations[key] = "只有学习成绩最高的一位学生才能考入顶尖大学。"
                elif key == 'q4':
                    explanations[key] = "最终排名是根据学生的学习成绩决定。"
                elif key == 'q5':
                    explanations[key] = "学习会消耗人生积分。"
                elif key == 'q6':
                    explanations[key] = "学习成本不是恒定的，会随着学习时间增长学习成本增高。"
                elif key == 'q7':
                    explanations[key] = "正确答案是15 (1+2+3+4+5 = 15)。"

        # 保存到 participant.vars 中（方便模板读取）
        player.participant.vars['quiz_explanations'] = explanations

        if has_error:
            # ✅ 改动4：阻止页面跳转（不显示上方红框）
            return "你必须正确回答所有问题才能进入下一页。"

    @staticmethod
    def vars_for_template(player: Player):
        explanations = player.participant.vars.get('quiz_explanations', {})
        # ✅ 改动5：传递 JSON 字典给前端（供 JS 在每题下显示）
        return dict(explanations_json=json.dumps(explanations, ensure_ascii=False))



class EnterID(Page):
    def is_displayed(player):  # 只在第1轮显示
        return player.round_number == 1

    form_model = 'player'
    form_fields = ['custom_id']


    @staticmethod
    def before_next_page(player, timeout_happened):
        player.participant.label = player.custom_id  # 填完编号后，存到 participant.label，方便后续导出/识别
        player.participant.vars["custom_id"] = player.custom_id

        # ✅ 将custom_id复制到所有轮次
        for round_num in range(1, C.NUM_ROUNDS + 1):
            round_player = player.in_round(round_num)
            round_player.custom_id = player.custom_id

class IntroWorld(Page):
    """输入编号后展示世界观文案，然后进入实验"""
    def is_displayed(player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player: Player):
        return dict(custom_id=player.custom_id)



class EffortDecision(Page):
    form_model = 'player'
    form_fields = ['effort']

    @staticmethod
    def vars_for_template(player: Player):
        if player.round_number in [1, 6]:# 🚫 第1轮 & 第6轮：不继承前一轮
            prev_round = None
        else:
            prev_round = player.in_round(player.round_number - 1)
        
        # ⬇️ 以下保持安全获取
        previous_round_rank_val = None#(如果存在上一轮 (prev_round) 并且它有属性 round_rank，就取出上一轮的名次；否则保持为 None)
        if prev_round and hasattr(prev_round, 'round_rank'):
            previous_round_rank_val = prev_round.round_rank
        
        # --- 残り人生ポイント ---（第1和第6轮没有上一轮 → 初始值0）
        previous_points = prev_round.points if prev_round else C.INITIAL_POINTS
        # 用于显示的余额 = 上一轮余额 + 本轮140点
        display_points = previous_points + C.ROUND_ALLOWANCE  # 本轮发放前 + 本轮发放后的数

        # --- 累積勉強時間の計算 ---
        if player.round_number in [1, 6]:
            # 第1・6ラウンドは新しい世界の始まり → 累積なし
            total_hours = 0
        else:
            # それ以外のラウンドは、現在ラウンド直前までの合計を表示
            total_hours = sum(p.effort or 0 for p in player.in_rounds(1, player.round_number - 1)
                            if (player.round_number <= 5 and p.round_number <= 5)
                            or (player.round_number > 5 and p.round_number > 5))

         # 🟢 世界内のラウンド番号（1～5にリセット表示）
        display_round = player.round_number if player.round_number <= 5 else player.round_number - 5   

        # 计算成本表供前端显示
        cost_table = [{'hours': h, 'cost': player.group.calculate_cost(h)} for h in C.EFFORT_OPTIONS] # 用统一成本函数生成表格

        # --- コスト表 ---返回字典
        return dict(
            current_points=display_points, # 前ラウンドの残高+本ラウンドに140ポイントを与える
            previous_points=previous_points,      # 用于说明文字里的“前回”
            round_allowance=C.ROUND_ALLOWANCE,  # ラウンドごとに140ポイントを与える（本轮发放的点数）
            previous_effort=prev_round.effort if prev_round else None,
            current_effort=player.field_maybe_none("effort"),  # 現在のラウンドで選択した努力時間（送信後にのみ表示されます）
            #round_rankはこのページは表示できない、プレイヤー全員の選択が終わってから表示できる。
            previous_round_rank=previous_round_rank_val, #前回ラウンドの学力ランキング
            current_total_hours=total_hours,  # 現在の累積学習時間
# コスト表
            cost_table=cost_table,  # コスト表
            a_linear=C.A_LINEAR,
            cost_formula_text="第1小时消耗10积分。之后学习时间成本每小时增加2积分",
            world_round=display_round,
        )



class ResultsWaitPage(WaitPage):
    def after_all_players_arrive (group: Group):
        group.set_rewards()
        if group.round_number in (5, C.NUM_ROUNDS):   # 第5轮和第10轮分别计算奖励
            group.determine_final_winner()      # 判定获胜者，第5轮结算前生，第10轮结算后生


class FinalResults(Page):
    def is_displayed(player: Player):  # 第5ラウンド（中間）・第10ラウンド（最終）結果ページ
        return player.round_number in [5,C.NUM_ROUNDS]  # C.NUM_ROUNDS 最後のラウンド目

    @staticmethod
    def vars_for_template(player: Player):
        # 世界内のラウンド番号（1～5にリセット表示）
        display_round = player.round_number if player.round_number <= 5 else player.round_number - 5
        # --- 确保变量总是存在 ---
        winner_bonus = 0
        loser_bonus = 0
        winner_flag = player.field_maybe_none('winner') or False

        # 根据阶段获取正确的奖励值
        is_first_half = player.round_number <= 5
        if is_first_half:
            winner_bonus = 2400
            loser_bonus = 300
        else:
            winner_bonus = 900
            loser_bonus = 800

        # --- 奖励计算 ---
        bonus = winner_bonus if winner_flag else loser_bonus   # 念のため合否判定の仮計算（奖励的人生ポイント）
        points_before_bonus = getattr(player, "points", 0)   # F5の結果（収入ポイント前）
        final_points = points_before_bonus + bonus # F5 + 収入ポイント
        
        # ラウンド履歴（フェーズごとに表示）
        all_history = []
        for r in range(1, player.round_number + 1):
            rp = player.in_round(r)
            all_history.append({
                "round": r,
                "effort": rp.field_maybe_none('effort') or 0,
                "points": rp.field_maybe_none('points') or 0,
            })

        # --- 按阶段过滤 ---
        history =   [row for row in all_history if (row["round"] <= 5)] if is_first_half else \
                    [row for row in all_history if (row["round"] > 5)]
    

        # 個人の勉強情報
        my_result = dict(
            id=player.id_in_group,
            points=player.points,                     # 収入ポイント前
            final_points=getattr(player, "final_points", 0),  # 収入ポイント後
            hours=player.total_hours,                 # 総勉強時間
            winner=getattr(player, "winner", False),
            rank=getattr(player, "rank", None) # ランキング
        )

        # ==== 返回模板变量 ====分数区
        return dict(
            points_before_bonus=points_before_bonus,  # F5（収入ポイント前の点数）
            final_points=final_points,  # F5 + 収入ポイント
            total_hours=player.total_hours,
            winner=player.winner, # プレイヤーが勝者であるかどうかを表示する
            winner_bonus=winner_bonus,  
            loser_bonus=loser_bonus,  
            bonus_text = ( 
                f"🎓 顶尖大学合格: +{winner_bonus} 积分"
                if player.winner 
                else f"📘 不合格: +{loser_bonus} 积分"
            ),
        # --- 其他显示 ---   
            my_result=my_result,  # 自分の結果を表示する。
            history=history,
            history_json=json.dumps(history, ensure_ascii=False),
            round_allowance=C.ROUND_ALLOWANCE,  # 显示每轮给予的点数
            is_first_half=is_first_half,
            world_round=display_round,
        )




class IntermissionPage(Page):
    """前半5回合结束后的世界切换（重置）页面"""
    def is_displayed(player):
        return player.round_number == 5  # 只在第5回合之后显示一次

    @staticmethod
    def vars_for_template(player: Player):
        # 判断是否合格
        winner_flag = player.field_maybe_none('winner') or False
        if winner_flag:
            message = "你在这个世界的努力结出了果实。"
        else:
            message = "你的人生只有一次。"
        
        # ✅ 从 participant.vars 取出累计数据（防止 player.total_hours 被清空）
        total_hours = player.participant.vars.get("first_half_hours", player.total_hours)
        final_points = player.participant.vars.get("first_half_points", player.final_points)

        # --- 消息分支 ---if player.session.vars.get('intermission_reset_done'):
        if winner_flag:
            scenario_text = "你在这个世界的努力结出了果实。"
        else:
            scenario_text = (
                "你的人生只有一次。<br>"
                "但是，如果有机会重新来过——<br>"
                "这一次，你会在怎样的社会，又会做出怎样的决定呢？"
            )


        return dict(
            scenario_text=scenario_text,
            total_hours=total_hours,
            final_points=final_points,
        )        

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        """
        前半終了後、後半世界の開始準備を行う（全員個別リセット）
        """

        # 後半フェーズに切替
        player.participant.vars['phase'] = 'second'

        # 自分のデータをリセット
        #player.effort = None               # 努力値クリア
        #player.round_rank = 0          #  # ランキングのクリア
        #player.winner = False
            
        # participant側の記録も後半用に初期化
        player.participant.vars['second_half_points'] = 0
        player.participant.vars['second_half_hours'] = 0
        player.participant.vars['points'] = 0     # ← 关键：重置 participant 里的余额为 0

        print(f"[Intermission] Player {player.id_in_group}: 前半段保存完毕，后半段准备开始。")



class LotteryDraw(Page):
    """抽选页面（第10轮显示第5轮抽选结果）"""
    def is_displayed(player):
        return player.round_number == C.NUM_ROUNDS

    @staticmethod
    def vars_for_template(player: Player):
        # ✅ 修改为从前半世界的数据中获取（收入差大的世界抽奖）
        final_points = player.participant.vars.get("first_half_points", 0)
        lottery_draws = player.participant.vars.get("first_half_draws", 0)
        lottery_numbers = player.participant.vars.get("first_half_numbers", [])
        leftover_points = final_points % C.LOTTERY_UNIT

        # 解析抽奖号码
        print(
            f"[LotteryDraw] Player {player.id_in_group}: "
            f"final_points={final_points}, draws={lottery_draws}, numbers={lottery_numbers}"
        )



        # 🟩 返回模板变量  返回 lottery_numbers，防止模板报错
        return dict(
            final_points=final_points,
            lottery_draws=lottery_draws,
            leftover_points=leftover_points,
            lottery_numbers=lottery_numbers,
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        """在页面离开时确认数据已保存"""
        # 数据已经在第5轮的 determine_final_winner 中保存
        final_points = player.participant.vars.get("first_half_points", 0)
        lottery_numbers = player.participant.vars.get("first_half_numbers", [])
        
        # 标记已经抽过奖
        player.did_draw = True
        
        print(f"[✅ Confirmed] Player {player.id_in_group} 前半世界抽奖数据确认。")







page_sequence = [ConsentForm,EnterID,QuizCheck,IntroWorld,EffortDecision,ResultsWaitPage,FinalResults,IntermissionPage,LotteryDraw,]

