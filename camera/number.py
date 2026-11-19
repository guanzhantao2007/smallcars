# number.py - Stage 1: minimal PP-OCR test for parking digit 1-6
#
# Goal: hold digits 1-6 in front of the camera, recognize the digit inside
# an adjustable ROI, and print measured result and processing time:
#   Digit: 4
#   Valid: True
#   Time: xx ms
# No multi-frame confirmation yet (stage 2), no UART output (stage 3).
#
# This file is self-contained: it only imports from maix, so it can run
# in MaixVision as a single file without the rest of the project folder.
# It does NOT modify any existing line-tracking / T-detect / UART code.
#
# API verified against official sources (do not trust unverified APIs):
#   - MaixPy doc "OCR" (wiki.sipeed.com/maixpy/doc/zh/vision/ocr.html):
#     requires MaixPy >= 4.6, model "/root/models/pp_ocr.mud" (PPOCRv3 det
#     + PPOCRv4 rec, pre-installed by firmware)
#   - official MaixPy example examples/vision/ai_vision/nn_pp_ocr.py
#   - MaixCDK header maix_nn_pp_ocr.hpp: detect(img, thresh, box_thresh)
#     auto-resizes any input image to the model input size
#   - MaixCDK header maix_nn_ocr_object.hpp: obj.box(x1..y4), obj.score,
#     obj.char_str()
#   - MaixPy doc "image ops": img.crop(x, y, w, h) returns a NEW image,
#     the original image is not modified

from maix import camera, display, image, nn, time, app

# ---------------- tunable parameters ----------------
CAM_W, CAM_H = 320, 240            # camera resolution in pixels, same as
                                   # the project standard (camera_config.py)
MODEL_PATH = "/root/models/pp_ocr.mud"    # PP-OCR model, ships with firmware
FONT_PATH = "/maixapp/share/font/ppocr_keys_v1.ttf"  # font to draw OCR text

# Digit ROI in the camera frame, [x, y, w, h], origin at top-left of the
# 320x240 image. PLACEHOLDER VALUE: must be calibrated on site so that the
# box covers the parking digit on the ground and avoids the black border
# lines of the parking slot.
DIGIT_ROI = [10, 30, 220, 180]

VALID_DIGITS = "123456"            # only these single chars are accepted
REC_MIN_SCORE = 0.20             # recognition confidence gate: obj.score
                                   # must reach this to accept a digit.
                                   # Calibrate on site (score is shown on
                                   # screen): keep it BELOW the lowest stable
                                   # score of correct reads (1-6) and ABOVE
                                   # the score of reflection misreads
DET_THRESH = 0.3                   # det model pixel prob threshold (official default)
BOX_THRESH = 0.6                   # box confidence threshold (official default)

# ---------------- model and font init ----------------
def init_ocr():
    # Load the official PP-OCR model and the font used to draw OCR text.
    # Returns the ocr object (nn.PP_OCR).
    ocr = nn.PP_OCR(MODEL_PATH)
    image.load_font("ppocr", FONT_PATH, size=20)
    image.set_default_font("ppocr")
    return ocr 


# ---------------- single-frame digit filter ----------------
def filter_digit(objs):
    # objs: iterable of nn.OCR_Object from ocr.detect()
    # Accept ONLY a single char in VALID_DIGITS AND confidence obj.score
    # >= REC_MIN_SCORE. Reflections may make the OCR read e.g. "14" or "7",
    # or a wrong digit with LOW confidence: both are rejected here.
    # If several valid digits pass the gate, keep the highest score one.
    # Returns (valid, digit, score); invalid -> (False, "", 0.0).
    best = ""
    best_score = 0.0
    for obj in objs:
        text = obj.char_str().strip()
        if len(text) == 1 and text in VALID_DIGITS and obj.score >= REC_MIN_SCORE:
            if obj.score > best_score:
                best = text
                best_score = obj.score
    if best == "":
        return False, "", 0.0
    return True, best, best_score


# ---------------- debug drawing ----------------
def draw_debug_number(img, objs, valid, digit, score):
    # Draw: ROI rect (green = valid this frame, red = invalid), status line
    # with MEASURED time, and the RAW ocr text of each detected box so that
    # reflection-induced misreads can be seen directly on screen.
    x, y, w, h = DIGIT_ROI
    color = image.COLOR_GREEN if valid else image.COLOR_RED
    img.draw_rect(x, y, w, h, color)
    if valid:
        img.draw_string(2, 2, "OK (%.2f)" % score,
                        image.COLOR_YELLOW, scale=1)
        img.draw_string(x + 2, y + h + 2, "Digit: %s" % digit, color)
    else:
        img.draw_string(2, 2, "NO DIGIT",
                        image.COLOR_RED, scale=1)
    # raw texts are in crop coordinates; just list them at the top-left
    #for i in range(len(objs)):
     #   txt = "%d raw:'%s' %.2f" % (i, objs[i].char_str(), objs[i].score)
      #  img.draw_string(2, 24 + i * 16, txt, image.COLOR_WHITE)

# ---------------- main test loop ----------------
def run():
    # Stage 1 test main loop: read frame -> crop ROI -> PP-OCR -> filter
    # digits -> draw -> print required 3-line result. The printed time is
    # measured with ticks_ms(), never guessed.
    ocr = init_ocr()
    # open camera at project resolution; use the model's input format so
    # detect() never complains about image format (same as official example)
    cam = camera.Camera(CAM_W, CAM_H, ocr.input_format())
    disp = display.Display()
    #frame = 0
    while not app.need_exit():
        img = cam.read()
       # t0 = time.ticks_ms()
        # crop the ROI and run detect+recognize on it (any size is auto
        # resized to model input by detect())
        crop = img.crop(DIGIT_ROI[0], DIGIT_ROI[1], DIGIT_ROI[2], DIGIT_ROI[3])
        objs = ocr.detect(crop, DET_THRESH, BOX_THRESH)
        valid, digit, score = filter_digit(objs)
        #ocr_ms = time.ticks_diff(time.ticks_ms(), t0)

        draw_debug_number(img, objs, valid, digit, score)
        disp.show(img)

        #frame += 1
        # required stage-1 output, printed every frame (OCR fps is low)
       # print("Digit: %s" % (digit if valid else "-"))
        #print("Valid: %s" % ("True" if valid else "False"))
        #print("Time: %d ms" % ocr_ms)
        # extra debug line: what the OCR really read (before filtering)
        #raws = []
        #for obj in objs:
         #   raws.append(obj.char_str())
        #print("Raw: %s" % raws)



