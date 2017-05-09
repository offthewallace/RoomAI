#!/bin/python
#coding:utf-8

import random
import copy
import roomai.abstract
import roomai
import logging

from TexasHoldemUtil import *


class TexasHoldemEnv(roomai.abstract.AbstractEnv):

    def __init__(self):
        self.logger         = roomai.get_logger()
        self.num_players    = 3 
        self.dealer_id      = int(random.random() * self.num_players)
        self.chips          = [1000 for i in xrange(self.num_players)]
        self.big_blind_bet  = 10

        logger = roomai.get_logger()

    # Before init, you need set the num_players, dealer_id, and chips
    #@override
    def init(self):
        isTerminal = False
        scores     = []

        allcards = []
        for i in xrange(13):
            for j in xrange(4):
                allcards.append(roomai.abstract.PokerCard(i, j))
        random.shuffle(allcards)
        hand_cards       = []
        for i in xrange(self.num_players):
              hand_cards.append(allcards[i*2:(i+1)*2])
        keep_cards   = allcards[self.num_players*2:self.num_players*2+5]

        ## public info
        small = (self.dealer_id + 1) % self.num_players
        big   = (self.dealer_id + 2) % self.num_players
        self.public_state                       = TexasHoldemPublicState()
        self.public_state.num_players           = self.num_players
        self.public_state.dealer_id             = self.dealer_id
        self.public_state.big_blind_bet         = self.big_blind_bet
        self.public_state.raise_account         = self.big_blind_bet

        self.public_state.is_quit               = [False for i in xrange(self.num_players)]
        self.public_state.num_quit              = 0
        self.public_state.is_allin              = [False for i in xrange(self.num_players)]
        self.public_state.num_allin             = 0
        self.public_state.is_expected_to_action = [True for i in xrange(self.num_players)]
        self.public_state.num_expected_to_action= self.public_state.num_players

        self.public_state.bets                  = [0 for i in xrange(self.num_players)]
        self.public_state.chips                 = self.chips
        self.public_state.stage                 = StageSpace.firstStage
        self.public_state.turn                  = self.next_player(big)
        self.public_state.public_cards          = []

        self.public_state.previous_id           = None
        self.public_state.previous_action       = None

        if self.public_state.chips[big] > self.big_blind_bet:
            self.public_state.chips[big] -= self.big_blind_bet
            self.public_state.bets[big]  += self.big_blind_bet
        else:
            self.public_state.bets[big]     = self.public_state.chips[big]
            self.public_state.chips[big]    = 0
            self.public_state.is_allin[big] = True
            self.public_state.num_allin    += 1
        self.public_state.max_bet       = self.public_state.bets[big]
        self.public_state.raise_account = self.big_blind_bet

        if self.public_state.chips[small] > self.big_blind_bet / 2:
            self.public_state.chips[small] -= self.big_blind_bet /2
            self.public_state.bets[small]  += self.big_blind_bet /2
        else:
            self.public_state.bets[small]     = self.public_state.chips[small]
            self.public_state.chips[small]    = 0
            self.public_state.is_allin[small] = True
            self.public_state.num_allin      += 1

        # private info
        self.private_state = TexasHoldemPrivateState()
        self.private_state.hand_cards       = [[] for i in xrange(self.num_players)]
        for i in xrange(self.num_players):
            self.private_state.hand_cards[i]  = copy.deepcopy(hand_cards[i])
        self.private_state.keep_cards = copy.deepcopy(keep_cards)

        ## person info
        self.person_states                      = [TexasHoldemPersonState() for i in xrange(self.num_players)]
        for i in xrange(self.num_players):
            self.person_states[i].id = i
            self.person_states[i].hand_cards = copy.deepcopy(hand_cards[i])
        self.person_states[self.public_state.turn].available_actions = self.available_actions(self.public_state)

        infos = self.gen_infos()

        if self.logger.level <= logging.DEBUG:
            self.logger.debug("TexasHoldemEnv.init: num_players = %d, dealer_id = %d, chip = %d, big_blind_bet = %d"%(\
                self.public_state.num_players,\
                self.public_state.dealer_id,\
                self.public_state.chips[0],\
                self.public_state.big_blind_bet
            ))

        return isTerminal, scores, infos, self.public_state, self.person_states, self.private_state

    ## we need ensure the action is valid
    #@Overide
    def forward(self, action):
        '''
        :param action: 
        :except: throw ValueError when the action is invalid at this time 
        '''

        if not self.is_action_valid(self.public_state, action):
            self.logger.critical("action=%s is invalid" % (action.get_key()))
            raise ValueError("action=%s is invalid" % (action.get_key()))


        isTerminal = False
        scores     = []
        infos      = []
        pu         = self.public_state
        pr         = self.private_state

        if action.option == TexasHoldemAction.Fold:
            self.action_fold(action)
        elif action.option == TexasHoldemAction.Check:
            self.action_check(action)
        elif action.option == TexasHoldemAction.Call:
            self.action_call(action)
        elif action.option == TexasHoldemAction.Raise:
            self.action_raise(action)
        elif action.option == TexasHoldemAction.AllIn:
            self.action_allin(action)
        else:
            raise Exception("action.option(%s) not in [Fold, Check, Call, Raise, AllIn]"%(action.option))
        pu.previous_id     = pu.turn
        pu.previous_action = action
        pu.turn            = self.next_player(pu.turn)

        # computing_score
        if self.is_compute_score():
            isTerminal = True
            scores = self.compute_score()
            ## need showdown
            if pu.num_quit + 1 < pu.num_players:
                pu.public_cards = pr.keep_cards[0:5]

        # enter into the next stage
        elif self.is_nextstage():
            add_cards = []
            if pu.stage == StageSpace.firstStage:   add_cards = pr.keep_cards[0:3]
            if pu.stage == StageSpace.secondStage:  add_cards = [pr.keep_cards[3]]
            if pu.stage == StageSpace.thirdStage:   add_cards = [pr.keep_cards[4]]

            pu.public_cards.extend(add_cards)
            pu.stage                      = pu.stage + 1
            pu.turn                       = (pu.dealer_id + 1) % pu.num_players
            pu.is_expected_to_action      = [True for i in xrange(pu.num_players)]
            pu.num_expected_to_action     = self.public_state.num_players

        self.person_states[self.public_state.previous_id].available_actions = None
        self.person_states[self.public_state.turn].available_actions        = self.available_actions(self.public_state)
        infos = self.gen_infos()

        if self.logger.level <= logging.DEBUG:
            self.logger.debug("TexasHoldemEnv.forward: num_quit+num_allin = %d+%d = %d, action = %s, stage = %d"%(\
                self.public_state.num_quit,\
                self.public_state.num_allin,\
                self.public_state.num_quit + self.public_state.num_allin,\
                action.get_key(),\
                self.public_state.stage\
            ))

        return isTerminal, scores, infos, self.public_state, self.person_states, self.private_state

    #override
    @classmethod
    def compete(cls, env, players):
        total_scores = [0    for i in xrange(len(players))]
        count        = 0

        ## the first match
        env.chips           = [5000 for i in xrange(len(players))]
        env.num_players     = len(players)
        env.dealer_id       = int(random.random * len(players))
        env.big_blind_bet   = 100

        isTerminal, _, infos, public, persons, private = env.init()
        for i in xrange(len(players)):
            players[i].receive_info(infos[i])
        while isTerminal == False:
            turn = public.turn
            action = players[turn].take_action()
            isTerminal, scores, infos, public, persons, private = env.forward(action)
            for i in xrange(len(players)):
                players[i].receive_info(infos[i])

        for i in xrange(len(players)):  total_scores[i] += scores[i]
        count += 1

        ## the following matches
        while True:
            dealer = (env.public_state.dealer_id + 1)%len(players)
            while env.public_state.chips[dealer]  == 0:
                dealer = (env.public_state.dealer_id + 1) % len(players)
            next_players_id = []  ## the available players (who still have bets) for the next match
            next_chips      = []
            next_dealer_id  = -1
            for i in xrange(len(env.public_state.chips)):
                if env.public_state.chips[i] > 0:
                    next_players_id.append(i)
                    next_chips.append(env.public_state.chips[i])
                    if i == dealer: next_dealer_id = len(next_players_id) - 1

            if len(next_players_id) == 1: break;

            if count % 10 == 0:
                env.big_blind_bet = env.big_blind_bet + 100
            env.chips       = next_chips
            env.dealer_id   = next_dealer_id
            env.num_players = len(next_players_id)
            
            isTerminal, scores, infos, public, persons, private = env.init()
            for i in xrange(len(next_players_id)):
                idx = next_players_id[i]
                players[idx].receive_info(infos[i])
            while isTerminal == False:
                turn = public.turn
                idx = next_players_id[turn]
                action = players[idx].take_action()
                isTerminal, scores, infos, public, persons, private = env.forward(action)
                for i in xrange(len(next_players_id)):
                    idx = next_players_id[i]
                    players[idx].receive_info(infos[i])

            for i in xrange(len(next_players_id)):
                idx = next_players_id[i]
                total_scores[idx] += scores[i]
            count += 1

        for i in xrange(len(players)): total_scores[i] /= count * 1.0
        return total_scores;


    def gen_infos(self):
        infos = [TexasHoldemInfo() for i in xrange(self.public_state.num_players)]
        for i in xrange(len(infos)):
            infos[i].person_state = copy.deepcopy(self.person_states[i])
        for i in xrange(len(infos)):
            infos[i].public_state = copy.deepcopy(self.public_state)
        return infos

    def next_player(self,i):
        pu = self.public_state
        if pu.num_expected_to_action == 0:
            return -1

        p = (i+1)%pu.num_players
        while pu.is_expected_to_action[p] == False:
            p = (p+1)%pu.num_players
        return p


    def is_nextstage(self):
        '''
        :return: 
        A boolean variable indicates whether is it time to enter the next stage
        '''
        pu = self.public_state
        return pu.num_expected_to_action == 0

    def is_compute_score(self):
        '''
        :return: 
        A boolean variable indicates whether is it time to compute scores
        '''
        pu = self.public_state

        if pu.num_players == pu.num_quit + 1:
            return True

        # below need showdown

        if pu.num_players ==  pu.num_quit + pu.num_allin + 1 and pu.num_expected_to_action == 0:
            return True

        if pu.stage == StageSpace.fourthStage and self.is_nextstage():
            return True

        return False

    def compute_score(self):
        '''
        :return: a score array
        '''
        pu = self.public_state
        pr = self.private_state

        ## compute score before showdown, the winner takes all
        if pu.num_players  ==  pu.num_quit + 1:
            scores = [0 for i in xrange(pu.num_players)]
            for i in xrange(pu.num_players):
                if pu.is_quit[i] == False:
                    scores[i] = sum(pu.bets)
                    break

        ## compute score after showdown
        else:
            scores                = [0 for i in xrange(pu.num_players)]
            playerid_pattern_bets = [] #for not_quit players
            for i in xrange(pu.num_players):
                if pu.is_quit[i] == True: continue
                hand_pattern = self.cards2pattern(pr.hand_cards[i], pr.keep_cards)
                playerid_pattern_bets.append((i,hand_pattern,pu.bets[i]))
            playerid_pattern_bets.sort(key=lambda x:x[1], cmp=self.compare_patterns)

            pot_line = 0
            previous = None
            tmp_playerid_pattern_bets      = []
            for i in xrange(len(playerid_pattern_bets)-1,-1,-1):
                if previous == None:
                    tmp_playerid_pattern_bets.append(playerid_pattern_bets[i])
                    previous = playerid_pattern_bets[i]
                elif self.compare_patterns(playerid_pattern_bets[i][1], previous[1]) == 0:
                    tmp_playerid_pattern_bets.append(playerid_pattern_bets[i])
                    previous = playerid_pattern_bets[i]
                else:
                    tmp_playerid_pattern_bets.sort(key = lambda x:x[2])
                    for k in xrange(len(tmp_playerid_pattern_bets)):
                        num1          = len(tmp_playerid_pattern_bets) - k
                        sum1          = 0
                        max_win_score = pu.bets[tmp_playerid_pattern_bets[k][0]]
                        for p in xrange(pu.num_players):    sum1      += min(max(0, pu.bets[p] - pot_line), max_win_score)
                        for p in xrange(k, len(tmp_playerid_pattern_bets)):       scores[p] += sum1 / num1
                        scores[pu.dealer_id] += sum1 % num1
                        if pot_line <= max_win_score:
                            pot_line = max_win_score
                    tmp_playerid_pattern_bets = []
                    tmp_playerid_pattern_bets.append(playerid_pattern_bets[i])
                    previous = playerid_pattern_bets[i]


            if len(tmp_playerid_pattern_bets) > 0:
                tmp_playerid_pattern_bets.sort(key = lambda  x:x[2])
                for i in xrange(len(tmp_playerid_pattern_bets)):
                    num1 = len(tmp_playerid_pattern_bets) - i
                    sum1 = 0
                    max_win_score = pu.bets[tmp_playerid_pattern_bets[i][0]]
                    for p in xrange(pu.num_players):
                        sum1 += min(max(0, pu.bets[p] - pot_line), max_win_score)
                    for p in xrange(i, len(tmp_playerid_pattern_bets)):
                        scores[tmp_playerid_pattern_bets[p][0]] += sum1 / num1
                    scores[pu.dealer_id] += sum1 % num1
                    if pot_line <= max_win_score: pot_line = max_win_score
        for p in xrange(pu.num_players):
            pu.chips[p] += scores[p]
            scores[p]   -= pu.bets[p]
        return scores


    def action_fold(self, action):
        pu = self.public_state
        pu.is_quit[pu.turn] = True
        pu.num_quit += 1

        pu.is_expected_to_action[pu.turn] = False
        pu.num_expected_to_action        -= 1

    def action_check(self, action):
        pu = self.public_state
        pu.is_expected_to_action[pu.turn] = False
        pu.num_expected_to_action        -= 1

    def action_call(self, action):
        pu = self.public_state
        pu.chips[pu.turn] -= action.price
        pu.bets[pu.turn]  += action.price
        pu.is_expected_to_action[pu.turn] = False
        pu.num_expected_to_action        -= 1

    def action_raise(self, action):
        pu = self.public_state

        pu.raise_account   = action.price + pu.bets[pu.turn] - pu.max_bet
        pu.chips[pu.turn] -= action.price
        pu.bets[pu.turn]  += action.price
        pu.max_bet         = pu.bets[pu.turn]

        pu.is_expected_to_action[pu.turn] = False
        pu.num_expected_to_action        -= 1
        p = (pu.turn + 1)%pu.num_players
        while p != pu.turn:
            if pu.is_allin[p] == False and pu.is_quit[p] == False and pu.is_expected_to_action[p] == False:
                pu.num_expected_to_action   += 1
                pu.is_expected_to_action[p]  = True
            p = (p + 1) % pu.num_players


    def action_allin(self, action):
        pu = self.public_state

        pu.is_allin[pu.turn]   = True
        pu.num_allin          += 1

        pu.bets[pu.turn]      += action.price
        pu.chips[pu.turn]      = 0

        pu.is_expected_to_action[pu.turn] = False
        pu.num_expected_to_action        -= 1
        if pu.bets[pu.turn] > pu.max_bet:
            pu.max_bet = pu.bets[pu.turn]
            p = (pu.turn + 1) % pu.num_players
            while p != pu.turn:
                if pu.is_allin[p] == False and pu.is_quit[p] == False and pu.is_expected_to_action[p] == False:
                    pu.num_expected_to_action  += 1
                    pu.is_expected_to_action[p] = True
                p = (p + 1) % pu.num_players

#####################################Utils Function ##############################
    @classmethod
    def cards2pattern(cls, hand_cards, remaining_cards):
        point2cards = dict()
        for c in hand_cards + remaining_cards:
            if c.point in point2cards:
                point2cards[c.point].append(c)
            else:
                point2cards[c.point] = [c]
        for p in point2cards:
            point2cards[p].sort(roomai.abstract.PokerCard.compare)

        suit2cards = dict()
        for c in hand_cards + remaining_cards:
            if c.suit in suit2cards:
                suit2cards[c.suit].append(c)
            else:
                suit2cards[c.suit] = [c]
        for s in suit2cards:
            suit2cards[s].sort(roomai.abstract.PokerCard.compare)

        num2point = [[], [], [], [], []]
        for p in point2cards:
            num = len(point2cards[p])
            num2point[num].append(p)
        for i in xrange(5):
            num2point[num].sort()

        sorted_point = []
        for p in point2cards:
            sorted_point.append(p)
        sorted_point.sort()

        ##straight_samesuit
        for s in suit2cards:
            if len(suit2cards[s]) >= 5:
                numStraight = 1
                for i in xrange(len(suit2cards[s]) - 2, -1, -1):
                    if suit2cards[s][i].point == suit2cards[s][i + 1].point - 1:
                        numStraight += 1
                    else:
                        numStraight = 1

                    if numStraight == 5:
                        pattern = AllCardsPattern["Straight_SameSuit"]
                        pattern[6] = suit2cards[s][i:i + 5]
                        return pattern

        ##4_1
        if len(num2point[4]) > 0:
            p4 = num2point[4][0]
            p1 = -1
            for i in xrange(len(sorted_point) - 1, -1, -1):
                if sorted_point[i] != p4:
                    p1 = sorted_point[i]
                    break
            pattern = AllCardsPattern["4_1"]
            pattern[6] = point2cards[p4][0:4]
            pattern[6].append(point2cards[p1][0])
            return pattern

        ##3_2
        if len(num2point[3]) >= 1:
            pattern = AllCardsPattern["3_2"]

            if len(num2point[3]) == 2:
                p3 = num2point[3][1]
                pattern[6] = point2cards[p3][0:3]
                p2 = num2point[3][0]
                pattern[6].append(point2cards[p2][0])
                pattern[6].append(point2cards[p2][1])
                return pattern

            if len(num2point[2]) >= 1:
                p3 = num2point[3][0]
                pattern[6] = point2cards[p3][0:3]
                p2 = num2point[2][len(num2point[2]) - 1]
                pattern[6].append(point2cards[p2][0])
                pattern[6].append(point2cards[p2][1])
                return pattern

        ##SameSuit
        for s in suit2cards:
            if len(suit2cards[s]) >= 5:
                pattern = AllCardsPattern["SameSuit"]
                len1 = len(suit2cards[s])
                pattern[6] = suit2cards[s][len1 - 5:len1]
                return pattern

        ##Straight_DiffSuit
        numStraight = 1
        for idx in xrange(len(sorted_point) - 2, -1, -1):
            if sorted_point[idx] + 1 == sorted_point[idx]:
                numStraight += 1
            else:
                numStraight = 1

            if numStraight == 5:
                pattern = AllCardsPattern["Straight_DiffSuit"]
                for p in xrange(idx, idx + 5):
                    point = sorted_point[p]
                    pattern[6].append(point2cards[point][0])
                return pattern

        ##3_1_1
        if len(num2point[3]) == 1:
            pattern = AllCardsPattern["3_1_1"]

            p3 = num2point[3][0]
            pattern[6] = point2cards[p3][0:3]

            num = 0
            for i in xrange(len(sorted_point) - 1, -1, -1):
                p = sorted_point[i]
                if p != p3:
                    pattern[6].append(point2cards[p][0])
                    num += 1
                if num == 2:    break
            return pattern

        ##2_2_1
        if len(num2point[2]) >= 2:
            pattern = AllCardsPattern["2_2_1"]
            p21 = num2point[2][len(num2point[2]) - 1]
            for c in point2cards[p21]:
                pattern[6].append(c)
            p22 = num2point[2][len(num2point[2]) - 2]
            for c in point2cards[p22]:
                pattern[6].append(c)

            flag = False
            for i in xrange(len(sorted_point) - 1, -1, -1):
                p = sorted_point[i]
                if p != p21 and p != p22:
                    c = point2cards[p][0]
                    pattern[6].append(c)
                    flag = True
                if flag == True:    break;
            return pattern

        ##2_1_1_1
        if len(num2point[2]) == 1:
            pattern = AllCardsPattern["2_1_1_1"]
            p2 = num2point[2][0]
            pattern[6] = point2cards[p2][0:2]
            num = 0
            for p in xrange(len(sorted_point) - 1, -1, -1):
                p1 = sorted_point[p]
                if p1 != p2:
                    pattern[6].append(point2cards[p1][0])
                if num == 3:    break
            return pattern

        ##1_1_1_1_1
        pattern = AllCardsPattern["1_1_1_1_1"]
        count = 0
        for i in xrange(len(sorted_point) - 1, -1, -1):
            p = sorted_point[i]
            for c in point2cards[p]:
                pattern[6].append(c)
                count += 1
                if count == 5: break
            if count == 5: break
        return pattern

    @classmethod
    def compare_handcards(cls, hand_card0, hand_card1, keep_cards):
        pattern0 = TexasHoldemEnv.cards2pattern(hand_card0, keep_cards)
        pattern1 = TexasHoldemEnv.cards2pattern(hand_card1, keep_cards)

        diff = cls.compare_patterns(pattern0, pattern1)
        return diff

    @classmethod
    def compare_patterns(cls, p1, p2):
        if p1[5] != p2[5]:
            return p1[5] - p2[5]
        else:
            for i in xrange(5):
                if p1[6][i] != p2[6][i]:
                    return p1[6][i] - p2[6][i]
            return 0

    @classmethod
    def available_actions(cls, public_state):
        pu = public_state
        turn = pu.turn
        key_actions = dict()

        ## for fold
        action = TexasHoldemAction(TexasHoldemAction.Fold + "_0")
        if cls.is_action_valid(public_state, action):
            key_actions[action.get_key()] = action

        ## for check
        if pu.bets[turn] == pu.max_bet:
            action = TexasHoldemAction(TexasHoldemAction.Check + "_0")
            if cls.is_action_valid(public_state, action):
                key_actions[action.get_key()] = action

        ## for call
        if pu.bets[turn] != pu.max_bet and pu.chips[turn] > pu.max_bet - pu.bets[turn]:
            action = TexasHoldemAction(TexasHoldemAction.Call + "_%d" % (pu.max_bet - pu.bets[turn]))
            if cls.is_action_valid(public_state, action):
                key_actions[action.get_key()] = action

        ## for raise
        if pu.bets[turn] != pu.max_bet and pu.chips[turn] > pu.max_bet - pu.bets[turn] + pu.raise_account:
            num = (pu.chips[turn] - (pu.max_bet - pu.bets[turn])) / pu.raise_account
            for i in xrange(1, num + 1):
                action = TexasHoldemAction(
                    TexasHoldemAction.Raise + "_%d" % ((pu.max_bet - pu.bets[turn]) + pu.raise_account * i))
                if cls.is_action_valid(public_state, action):
                    key_actions[action.get_key()] = action

        ## for all in
        action = TexasHoldemAction(TexasHoldemAction.AllIn + "_%d" % (pu.chips[turn]))
        if cls.is_action_valid(public_state, action):
            key_actions[action.get_key()] = action

        return key_actions

    @classmethod
    def is_action_valid(cls, public_state, action):
        pu = public_state

        if (not isinstance(public_state, TexasHoldemPublicState)) or (not isinstance(action, TexasHoldemAction)):
            return False

        if pu.is_allin[pu.turn] == True or pu.is_quit[pu.turn] == True:
            return False
        if pu.chips[pu.turn] == 0:
            return False

        if action.option == TexasHoldemAction.Fold:
            return True

        elif action.option == TexasHoldemAction.Check:
            if pu.bets[pu.turn] == pu.max_bet:
                return True
            else:
                return False

        elif action.option == TexasHoldemAction.Call:
            if action.price == pu.max_bet - pu.bets[pu.turn]:
                return True
            else:
                return False

        elif action.option == TexasHoldemAction.Raise:
            raise_account = action.price - (pu.max_bet - pu.bets[pu.turn])
            if raise_account == 0:    return False
            if raise_account % pu.raise_account == 0:
                return True
            else:
                return False
        elif action.option == TexasHoldemAction.AllIn:
            if action.price == pu.chips[pu.turn]:
                return True
            else:
                return False
        else:
            raise Exception("Invalid action.option" + action.option)
