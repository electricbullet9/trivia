import itertools
import re
import time
from collections import defaultdict

from colorama import Fore, Style

import search

punctuation_to_none = str.maketrans({key: None for key in "!\"#$%&\'()*+,-.:;<=>?@[\\]^_`{|}~�"})
punctuation_to_space = str.maketrans({key: " " for key in "!\"#$%&\'()*+,-.:;<=>?@[\\]^_`{|}~�"})


async def answer_question(question, original_answers):
    print("Searching")
    start = time.time()

    answers = []
    for ans in original_answers:
        answers.append(ans.translate(punctuation_to_none))
        answers.append(ans.translate(punctuation_to_space))
    answers = list(dict.fromkeys(answers))
    print(answers)

    question_lower = question.lower()

    reverse = "NOT" in question or\
              ("least" in question_lower and "at least" not in question_lower) or\
              "NEVER" in question

    quoted = re.findall('"([^"]*)"', question_lower)  # Get all words in quotes
    no_quote = question_lower
    for quote in quoted:
        no_quote = no_quote.replace(f"\"{quote}\"", "1placeholder1")

    question_keywords = search.find_keywords(no_quote)
    for quote in quoted:
        question_keywords[question_keywords.index("1placeholder1")] = quote

    print(question_keywords)
    search_results = await search.search_google("+".join(question_keywords), 5)

    search_text = [x.translate(punctuation_to_none) for x in await search.get_clean_texts(search_results)]

    best_answer = await __search_method1(search_text, question_keywords, answers, reverse)
    if best_answer == "":

        print(f"{Fore.GREEN}No answer found! trying method 3{Style.RESET_ALL}\n")

        # Get key nouns for Method 3
        key_nouns = set(quoted)

        if len(key_nouns) == 0:

            key_nouns.update(search.find_nouns(question, len(re.findall(r'\w+', question))))

            key_nouns -= {"type"}

            key_nouns = [noun.lower() for noun in key_nouns]
            print(f"Question nouns: {key_nouns}")
            answer3 = await __search_method3(list(set(question_keywords)), key_nouns, original_answers, reverse)
            print(f"{Fore.GREEN}{answer3}{Style.RESET_ALL}")

    if best_answer != "":
        print(f"{Fore.GREEN}{best_answer}{Style.RESET_ALL}\n")

    print(f"Search took {time.time() - start} seconds")


async def __search_method1(texts, question_keywords, answers, reverse):
    """
    Returns the answer with the maximum/minimum number of exact occurrences in the texts.
    :param texts: List of text to analyze
    :param answers: List of answers
    :param reverse: True if the best answer occurs the least, False otherwise
    :return: Answer that occurs the most/least in the texts, empty string if there is a tie
    """
    print("Running method 1")
    weighted = get_proximity_scores(texts, answers, question_keywords)

    # If not all answers have count of 0 and the best value doesn't occur more than once, return the best answer
    best_value = min(weighted.values()) if reverse else max(weighted.values())
    if not all(c == 0 for c in weighted.values()) and list(weighted.values()).count(best_value) == 1:
        return min(weighted, key=weighted.get) if reverse else max(weighted, key=weighted.get)
    return ""


async def __search_method2(texts, answers, reverse):
    """
    Return the answer with the maximum/minimum number of keyword occurrences in the texts.
    :param texts: List of text to analyze
    :param answers: List of answers
    :param reverse: True if the best answer occurs the least, False otherwise
    :return: Answer whose keywords occur most/least in the texts
    """
    print("Running method 2")
    counts = {answer: {keyword: 0 for keyword in search.find_keywords(answer)} for answer in answers}

    for text in texts:
        for keyword_counts in counts.values():
            for keyword in keyword_counts:
                keyword_counts[keyword] += len(re.findall(f" {keyword} ", text))

    print(counts)
    counts_sum = {answer: sum(keyword_counts.values()) for answer, keyword_counts in counts.items()}

    if not all(c == 0 for c in counts_sum.values()):
        return min(counts_sum, key=counts_sum.get) if reverse else max(counts_sum, key=counts_sum.get)
    return ""


async def __search_method3(question_keywords, question_key_nouns, answers, reverse):
    """
    Returns the answer with the maximum number of occurrences of the question keywords in its searches.
    :param question_keywords: Keywords of the question
    :param question_key_nouns: Key nouns of the question
    :param answers: List of answers
    :param reverse: True if the best answer occurs the least, False otherwise
    :return: Answer whose search results contain the most keywords of the question
    """
    print("Running method 3")
    search_results = await search.multiple_search(answers, 5)
    print("Search processed")
    answer_lengths = list(map(len, search_results))
    search_results = itertools.chain.from_iterable(search_results)

    texts = [x.translate(punctuation_to_none) for x in await search.get_clean_texts(search_results)]
    print("URLs fetched")
    answer_text_map = {}
    for idx, length in enumerate(answer_lengths):
        answer_text_map[answers[idx]] = texts[0:length]
        del texts[0:length]

    keyword_scores = {answer: 0 for answer in answers}
    noun_scores = {answer: 0 for answer in answers}

    # Create a dictionary of word to type of score so we avoid searching for the same thing twice in the same page
    word_score_map = defaultdict(list)
    for word in question_keywords:
        word_score_map[word].append("KW")
    for word in question_key_nouns:
        word_score_map[word].append("KN")

    answer_noun_scores_map = {}
    for answer, texts in answer_text_map.items():
        keyword_score = 0
        noun_score = 0
        noun_score_map = defaultdict(int)

        for text in texts:
            for keyword, score_types in word_score_map.items():
                score = len(re.findall(f" {keyword} ", text))
                if "KW" in score_types:
                    keyword_score += score
                if "KN" in score_types:
                    noun_score += score
                    noun_score_map[keyword] += score

        keyword_scores[answer] = keyword_score
        noun_scores[answer] = noun_score
        answer_noun_scores_map[answer] = noun_score_map

    print()
    print("\n".join([f"{answer}: {dict(scores)}" for answer, scores in answer_noun_scores_map.items()]))
    print()

    print(f"Keyword scores: {keyword_scores}")
    print(f"Noun scores: {noun_scores}")
    if set(noun_scores.values()) != {0}:
        return min(noun_scores, key=noun_scores.get) if reverse else max(noun_scores, key=noun_scores.get)
    if set(keyword_scores.values()) != {0}:
        return min(keyword_scores, key=keyword_scores.get) if reverse else max(keyword_scores, key=keyword_scores.get)
    return ""


def get_proximity_scores(texts, answers, question_keywords):

    counts = {answer.lower(): 0 for answer in answers}
    proximity_scores = {answer.lower(): 0 for answer in answers}
    question_indexes = {question.lower(): [] for question in question_keywords}
    answer_indexes = {answer.lower(): [] for answer in answers}

    # file = open("testlog.txt", "w")
    # for text in texts:
    #     file.write(text)
    # file.close()

    word_list = []
    for text in texts:
        for answer in counts:
            counts[answer] += len(re.findall(f" {answer} ", text))
        word_list += re.split(r"\s", text)

    for i, j in enumerate(word_list):
        for answer in answer_indexes:
            if search.matches_term(answer, word_list, i):
                answer_indexes[answer].append(i)

        for question in question_indexes:
            if search.matches_term(question, word_list, i):
                question_indexes[question].append(i)

    # print(answer_indexes)
    # print(question_indexes)
    for i in answer_indexes:
        # loops through the 3 answers
        length = 0
        total = 0
        for j in answer_indexes[i]:
            # loops through every index
            current_min = 0
            for x in question_indexes:
                # loops through question keywords
                if len(question_indexes[x]) > 0:
                    temp_total = search.find_nearest(question_indexes[x], j)
                    # finds the nearest value in the array, returns the difference
                    if temp_total < current_min or current_min == 0:
                        current_min = temp_total

            total += current_min
            length += 1
        if length != 0:
            proximity_scores[i] = total/length
    print("proximity:\t"+str(proximity_scores))
    print("totals:\t\t"+str(counts))
    weighted = get_weighted_scores(proximity_scores, counts)
    print("weighted:\t"+str(weighted))
    return weighted


def get_weighted_scores(prox, counts):
    total_weight = max(prox.values())*1.2
    multipliers = prox
    for items in prox:
        if prox[items] != 0:
            multipliers[items] = (total_weight - prox[items])/(total_weight/2)

    for answers in counts:
        counts[answers] = counts[answers] * multipliers[answers]

    return counts

