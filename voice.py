# THE VOICE-INATOR 3000
#
# abcdefghijklmnopqrstuvwxyz
# abdefghijklmnopqrstuvwyz∫чʌIʊαŋε
#                             ^^^
# yes this is alpha, no we are not changing it

import sounddevice as sd
import soundfile as sf
import numpy as np
import keyboard
import time
import re
import base64

TESTMODE = False
DEBUG = True

print(sd.query_devices())
print(" ")

SAMPLE_PATH = __file__[:-8] + "/samples/"

DEVICE = sd.query_devices(kind="input")["index"]
TESTINGDEVICE = sd.query_devices(kind="output")["index"]

chatkeybind = "/" # chat key
PTT_KEY = "end" # push to talk key

chat = False
message = ''#base64.b64decode("").decode("utf-8").lower() #<-- this is for testing, use if needed.

# in-memory cache: key -> (data, samplerate, duration)
cache = {}

# how much silence to insert between consecutive letters (seconds)
LETTER_GAP = 0.00
PUNCTUATION_GAPS = {
    '↓': 0.03,
    ' ': 0.15,
    '.': 1.00,
    ',': 0.40
    }

def tonumber(n): # no, this is number to string, the developer is stupid
    try:
        number = int(n)
    except:
        return n

    ones = [
        "zero", "one", "two", "three", "four",
        "five", "six", "seven", "eight", "nine",
        "ten", "eleven", "twelve", "thirteen",
        "fourteen", "fifteen", "sixteen",
        "seventeen", "eighteen", "nineteen"
    ]

    tens = [
        "", "", "twenty", "thirty", "forty",
        "fifty", "sixty", "seventy",
        "eighty", "ninety"
    ]

    scales = [
        "",
        "thousand",
        "million",
        "billion",
        "trillion",
        "quadrillion",
        "quintillion",
        "sextillion",
        "septillion",
        "octillion",
        "nonillion"
    ]

    def three_digits(num):
        words = []

        if num >= 100:
            words.append(ones[num // 100])
            words.append("hundred")
            num %= 100

        if num >= 20:
            words.append(tens[num // 10])
            num %= 10

        if num > 0:
            words.append(ones[num])

        return "-".join(words) if len(words) == 2 else " ".join(words)

    if number == 0:
        return "zero"

    if number < 0:
        return "negative " + tonumber(-number)

    groups = []

    while number > 0:
        groups.append(number % 1000)
        number //= 1000

    result = []

    for i in range(len(groups) - 1, -1, -1):
        if groups[i] != 0:
            result.append(three_digits(groups[i]))
            if i < len(scales):
                result.append(scales[i])

    return " ".join(result)

def _to_mono(data):
    if data.ndim > 1:
        return data.mean(axis=1)
    return data

def _resample(data, orig_sr, target_sr):
    if orig_sr == target_sr:
        return data
    duration = len(data) / orig_sr
    new_len = int(round(duration * target_sr))
    old_x = np.linspace(0, duration, num=len(data), endpoint=False)
    new_x = np.linspace(0, duration, num=new_len, endpoint=False)
    return np.interp(new_x, old_x, data)


def preload():
    chars = list("abdefghijklmnopqrstuvwyz") + ["sh", "ch", "long_i", "uh", 'oh', 'ah', 'ng']

    target_sr = None
    raw = {}

    # first pass: read everything, record shapes/rates for diagnostics
    for x in chars:
        file = SAMPLE_PATH + x + ".wav"
        try:
            data, samplerate = sf.read(file)
            raw[x] = (data, samplerate)
            if target_sr is None:
                target_sr = samplerate
        except Exception as exc:
            print(f"[preload] exception: {exc} ({file})")
    
    if DEBUG == True:
        print("CACHE:", cache.keys())
    
    if target_sr is None:
        print("[preload] no samples loaded at all - check SAMPLE_PATH")
        return

    # second pass: normalize + cache, warn about anything that looks off
    amplitudes = {}
    for x, (data, samplerate) in raw.items():
        original_shape = data.shape

        data = _to_mono(data)

        if samplerate != target_sr:
            print(f"[preload] '{x}.wav' is {samplerate}Hz, resampling to {target_sr}Hz")
            data = _resample(data, samplerate, target_sr)

        duration = len(data) / target_sr
        peak = float(np.abs(data).max()) if len(data) else 0.0
        amplitudes[x] = peak

        if original_shape != data.shape and len(original_shape) > 1:
            print(f"[preload] '{x}.wav' was multi-channel {original_shape}, converted to mono")

        if duration < 0.03:
            print(f"[preload] WARNING: '{x}.wav' is only {duration:.3f}s long - might be empty/cut off")

        if peak < 0.01:
            print(f"[preload] WARNING: '{x}.wav' peak amplitude is {peak:.5f} - likely near-silent")

        cache[x] = (data, target_sr, duration)

    # flag outliers relative to the rest of the set (catches one quiet file among otherwise normal ones, even if it's not silent in isolation)
    if amplitudes:
        median_peak = float(np.median(list(amplitudes.values())))
        for x, peak in amplitudes.items():
            if median_peak > 0 and peak < median_peak * 0.15:
                print(f"[preload] NOTE: '{x}.wav' is much quieter than other samples "
                      f"(peak {peak:.4f} vs median {median_peak:.4f}) - may sound silent in playback")


def play(key):
    if key not in cache:
        print(f"[play] no sample loaded for '{key}'")
        return
        
    data, samplerate, duration = cache[key]
    sd.play(data, samplerate, device=DEVICE)
    time.sleep(duration)


def build_message_audio(message):
    if not cache:
        return None, None

    samplerate = next(iter(cache.values()))[1]
    gap = np.zeros(int(LETTER_GAP * samplerate))

    chunks = []
    for x in message:
        if x in '., ↓':
            chunks.append(np.zeros(int(PUNCTUATION_GAPS[x] * samplerate)))
            continue

        sample_key = x
        if x == "∫":
            sample_key = "sh"
        if x == "ч":
            sample_key = "ch"
        if x == "I":
            sample_key = "long_i"
        if x == "ʌ":
            sample_key = "uh"
        if x == "ʊ":
            sample_key = "oh"
        if x == "α":
            sample_key = "ah"
        if x == "ŋ":
            sample_key = "ng"

        if sample_key not in cache:
            print(f"[build_message_audio] no sample for '{sample_key}'")
            continue

        data, sr, _ = cache[sample_key]
        chunks.append(data)
        chunks.append(gap)

    if not chunks:
        return None, None
    return np.concatenate(chunks), samplerate


def play_message(message):
    audio, samplerate = build_message_audio(message)
    if audio is None:
        return
    sd.play(audio, samplerate, device=DEVICE)
    sd.wait()


def pronounce(string):
    vowels = ["a", "e", "i", "o", "u", 'ʌ', 'I', 'ʊ', 'α', 'ι'] # a DIDNT run waway

    # the AWESOME!(factorial) punctiation
    string = string.replace('!', ',factorial.')
    string = string.replace('?', '.')
    string = string.replace('(', ',')
    string = string.replace(')', ',')
    string = string.replace("-", " ")

    # make slang actual WORDS.
    fix = {'z': 'zet', 'cpu': 'see p u', 'zinc': 'zink*', 'ts': 'this', 'ceo': 'see e o', 'co': 'corporation', 'tts': 'tee tee εs', "u": "you", 'r': 'are', 'ur': 'you are', 'pls': 'please', 'plz': 'please', 'thx': 'thanks', 'tmr': 'tomorrow', 'im': 'i am', 'idk': 'i dont know', 'ig': 'i guess', 'np': 'no problem', 'btw': 'by the way', 'ty': 'thank you', 'brb': 'be right back', 'gtg': 'gotta go', 'kys': 'kill yourself', 'kms': 'kill myself', 'ily': 'i love you', 'tysm': 'thank you so much', 'smth': 'something'}
    words = string.split()
    result = []
    for x in words:
        if x.strip(".,") in fix:
            result.append(fix[x.strip(".,")])
        else:
            result.append(x)
    string = " ".join(result)
    
    # make numbers cooler
    result = []
    words = string.split()
    for x in words:
        x = tonumber(x)
        result.append(x)
    string = " ".join(result)
    
    # uh to 'uh' sound (/ʌ/)
    string = string.replace("uh", "ʌ")

    # x to z
    exclude = {'xray', 'xray', 'xbox'}
    words = string.split()
    r = []
    for x in words:
        if x.lower() in exclude:
            r.append(x)
        elif x and x[0].lower() == 'x':
            r.append('z' + x[1:])
        else:
            r.append(x)
    string = " ".join(r)

    # the ng sound
    # whoever invented this owes me an apology
    exclude = {'finger', 'anger', 'stronger', 'mingle', 'fingers', 'fingering', 'angerly', 'angy', 'angry', 'stronger', 'strongest', 'young', 'younger', 'youngest', 'mingling', 'lingering', 'linger', 'english'}
    words = string.split()
    for i, v in enumerate(words):
        if not v in exclude:
            words[i] = v.replace('ng', 'ŋ')
    string = ' '.join(words)

    # x to ks
    # x.wav got promoted to 'unemployed'. congratulations!
    string = string.replace("x", "ks")

    # ou to u
    string = string.replace("ou", "u")

    # sh and ch sounds
    string = string.replace("sh", "∫")
    string = string.replace("ch", "ч")
    # english has 2 sounds for th.
    # we have 0. budget cuts.
    string = string.replace("th", "z")

    # c to k/s  (must run BEFORE silent-e removal, so "nice" sees its e)
    r = ""
    for i in range(len(string)):
        if string[i] == "c":
            if (
                i + 1 < len(string)
                and string[i + 1].lower() in ['ι', 'I', "e", "i", "y"]
            ):
                r += "s"
            else:
                r += "k"
        else:
            r += string[i]
    string = r

    # long i (sounds like "eye")
    words = string.split()
    for i, word in enumerate(words):
        # Pattern 1: "ie" ending with long i sound (pie, tie, die) -- not movie/cookie
        if word.endswith("ie") and len(word) > 2 and word[-3] not in "aeiou":
            words[i] = word[:-2] + "Ie"
        # Pattern 2: silent-e, "i_e" -- time, like, side, ride
        elif re.search(r"i[bcdfghjklmnpqrstvwxz]e$", word, re.IGNORECASE):
            words[i] = re.sub(r"i([bcdfghjklmnpqrstvwxz]e)$", r"I\1", word, flags=re.IGNORECASE)
    string = " ".join(words)

    # ee to i
    string = string.replace("ee", "i")

    # silent e on endings
    exclude = {"die", 'he', '∫e', 'ze', 'me', "tie", "be"}
    words = string.split()
    for i, word in enumerate(words):
        if word.endswith("e"):
            if not word in exclude:
                words[i] = word[:-1]
    string = " ".join(words)

    # u to a (uh) sound
    r = ""
    i = 0
    while i < len(string):
        if string[i] == "u":
            if i + 1 < len(string) and string[i + 1] == "r":
                r += "u"  # keep "ur" unchanged
            elif i + 1 < len(string) and string[i + 1].lower() not in vowels and string[i + 1] != " ":
                r += "ʌ"
            else:
                r += "u"
        else:
            r += string[i]
        i += 1
    string = r

    # y to short/long i sound
    r = ""
    exclude = {'try', 'my', 'fly'}
    for i, x in enumerate(string):
        if not x in exclude:
            if x == "y" and i > 0 and string[i - 1] != " ":
                x = "i"
        else:
            if x == "y" and i > 0 and string[i - 1] != " ":
                x = "I"
        r += x
    string = r

    # the ah sound department
    string = string.replace("ar", "αr")
    string = string.replace("all", "αl")
    # the oh sound in ow and oa
    string = string.replace("ow", "ʊ")
    string = string.replace("oa", "ʊ")
    # ue to u
    string = string.replace("ue", "u")
    # oo to u
    string = string.replace("oo", "u")
    # ph to f
    string = string.replace("ph", "f")
    # qu to q
    string = string.replace("qu", "q")

    # ght and igh department
    string = string.replace("igh", "I")
    string = string.replace("ght", "t")

    # collapse double letters
    r = ""
    last = ""
    for x in string:
        if x != last:
            r += x
        last = x
    string = r

    # prefixes (suffixes too i guess?) and other stuff (the pneumonoultramicroscopicsilicovolcaniconiosis department™)
    string = string.replace("pneumo", "neumo")
    string = string.replace("tion", "∫ʌŋ")
    string = string.replace("sion", "∫ʌn")
    string = string.replace("sian", "∫ʌn")
    string = string.replace("sial", "∫ʌl")

    # the stupid words (but less stupid) department
    exceptions = {'ʌltra': 'ultra', 'eŋinir': 'enjinir', 'чild': 'чIld', 'ziŋ': 'tiŋ', 'zink': 'tink'}
    for i, v in exceptions.items():
        string = string.replace(i, v)

    # exceptions (for really stupid words)
    # no english, you are wrong
    exceptions = {'tinks*': 'zinks', 'tink*': 'zink', 'zri': 'tri', 'ziŋ': 'ting', 'no': 'nʊ', 'go': 'gʊ', 'autist': 'αutizt', 'autism': 'αutizm', 'ut': 'αut', "mαrkipliers": 'mαrkiplIyers', "mαrkiplier": 'mαrkiplIyer', 'tini': 'tIni', 'чʌds': 'чuds', 'чʌd': 'чud', 'do': 'du', 'miself': 'mIself', 'islands': 'Ilands', 'island': 'Iland', 'fjords': 'fyords', 'fjord': 'fyord', 'faktorial': 'faktoriαl', 'awesom': 'αwesum', 'bekaʌs': 'bikʊz', 'nam': 'neim', 'gras': 'grαs', 'ventur': 'venчur', 'natur': 'naчur', 'fʌtur': 'fuчur', 'fitur': 'fiчur', 'aʌdit': 'audit', 'hei': 'hI', 'gʌis': 'gIs', 'gʌi': 'gI', 'bʌi': 'bI', 'bi': 'bI', 'whi': 'whI', 'wild': 'wIld', 'child': 'chIld', 'blind': 'blInd', 'mind': 'mInd', 'kind': 'kInd', 'find': 'fInd', '∫i': '∫I', "yeah": "yeh", 'hiriŋ': 'hIriŋ', 'heard': 'herd', 'stʌpid': 'stupit', "krimes": "kraymz", "krim": "kraym", 'talk': 'tαlk', 'wαls': 'wols', 'break': 'breyk', 'bread': 'bred', 'steak': 'steyk', 'great': 'greyt', 'heαrt': 'hαrt', 'learn': 'lern', 'eαrz': 'erz', 'hird': 'herd', 'peopl': 'pepul', 'ons': 'wʌns', 'knight': 'naIt', 'knif': 'naIf', 'tri': 'trI', 'knʊ': 'nʊw', 'breakfast': 'brekfʌst', 'pʌl': 'pul', 'zrʌgh': 'zrʊ', 'pʌ∫': 'pu∫', 'i': 'I', 'delisiʌs': 'deli∫iʌs', 'me': 'mi', 'mi': 'mI', 'kak': 'kayk', 'tʌgh': 'tʌf', 'zʌght': 'tʊht', 'hi': 'hI', 'want': 'wαnt'}
    words = string.split()
    for i, v in enumerate(words):
        if v.strip('.,') in exceptions:
            words[i] = exceptions[v.strip('.,')]
    string = ' '.join(words)

    # the EA Sports.
    string = string.replace("ea", "i")
    string = string.replace("eα", "i")

    string += "."
    if DEBUG == True: print(string)
    return string.strip("*")

def oninput(key):
    global chat
    global message

    if key.name == chatkeybind:
        chat = True
        keyboard.press_and_release("backspace")
        return

    if key.name == "space":
        message = message + " "
        keyboard.press_and_release("backspace")
        return

    if key.name == "backspace":
        message = message[:len(message) - 1]
        return

    if key.name == "enter":
        if chat == False:
            return
        
        keyboard.press(PTT_KEY)
        time.sleep(1)
        chat = False
        message = pronounce(message)
        play_message(message)
        message = ""
        time.sleep(2)
        keyboard.release(PTT_KEY)
        return

    if chat == True:
        approved = False
        for x in "abcdefghijklmnopqrstuvwxyz.,!1234567890":
            if x == key.name:
                approved = True

        if approved == False:
            return

        message = message + key.name
        
        keyboard.release(key.name)
        keyboard.press_and_release("backspace")


keyboard.on_press(oninput)
preload()

if TESTMODE == True:
    DEVICE = TESTINGDEVICE

while True:
    time.sleep(1)