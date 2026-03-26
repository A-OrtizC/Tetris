import numpy as np
import mss
import time
import pyautogui
import cv2
from datetime import datetime

BOARD_W = 10
BOARD_H = 20

_RAW_PIECES = {
    "C":[[[1,1],[1,1]]],

    "I":[
        [[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]],
        [[0,0,1,0],[0,0,1,0],[0,0,1,0],[0,0,1,0]],
        [[0,0,0,0],[0,0,0,0],[1,1,1,1],[0,0,0,0]],
        [[0,1,0,0],[0,1,0,0],[0,1,0,0],[0,1,0,0]]
    ],

    "T":[
        [[0,1,0],[1,1,1],[0,0,0]],
        [[0,1,0],[0,1,1],[0,1,0]],
        [[0,0,0],[1,1,1],[0,1,0]],
        [[0,1,0],[1,1,0],[0,1,0]]
    ],

    "L":[
        [[0,0,1],[1,1,1],[0,0,0]],
        [[0,1,0],[0,1,0],[0,1,1]],
        [[0,0,0],[1,1,1],[1,0,0]],
        [[1,1,0],[0,1,0],[0,1,0]]
    ],

    "J":[
        [[1,0,0],[1,1,1],[0,0,0]],
        [[0,1,1],[0,1,0],[0,1,0]],
        [[0,0,0],[1,1,1],[0,0,1]],
        [[0,1,0],[0,1,0],[1,1,0]]
    ],

    "S":[
        [[0,1,1],[1,1,0],[0,0,0]],
        [[0,1,0],[0,1,1],[0,0,1]],
        [[0,0,0],[0,1,1],[1,1,0]],
        [[1,0,0],[1,1,0],[0,1,0]]
    ],

    "Z":[
        [[1,1,0],[0,1,1],[0,0,0]],
        [[0,0,1],[0,1,1],[0,1,0]],
        [[0,0,0],[1,1,0],[0,1,1]],
        [[0,1,0],[1,1,0],[1,0,0]]
    ]
}

PIECES = {k:[np.array(r,dtype=np.int8) for r in v] for k,v in _RAW_PIECES.items()}

class Agent:

    FULL_ROW = (1 << BOARD_W) - 1

    def __init__(self):

        self.board = [0]*BOARD_H
        self.last_queue = None

        self.pieces = {}
        self.bounds = {}

        for p, rots in PIECES.items():

            self.pieces[p] = []
            self.bounds[p] = []

            for r in rots:

                coords = np.argwhere(r)
                ys = coords[:,0]
                xs = coords[:,1]

                min_x, max_x = xs.min(), xs.max()
                min_y, max_y = ys.min(), ys.max()

                self.bounds[p].append((min_x, max_x, min_y, max_y))

                self.pieces[p].append([(x-min_x, y-min_y) for y,x in coords])

    def get_heights(self, board):

        heights = [0]*BOARD_W

        for x in range(BOARD_W):
            for y in range(BOARD_H):
                if board[y] & (1 << x):
                    heights[x] = BOARD_H - y
                    break

        return heights

    def drop_piece(self, board, cells, x):

        heights = self.get_heights(board)

        y = BOARD_H

        for ox, oy in cells:

            col = x + ox
            if col < 0 or col >= BOARD_W:
                return None

            h = heights[col]
            py = BOARD_H - h - 1 - oy

            if py < y:
                y = py

        if y < 0:
            return None

        new_board = board.copy()

        for ox, oy in cells:
            bx = x + ox
            by = y + oy
            new_board[by] |= (1 << bx)

        return self.clear_lines(new_board)

    def clear_lines(self, board):

        new_board = []
        lines = 0

        for row in board:
            if row == self.FULL_ROW:
                lines += 1
            else:
                new_board.append(row)

        return [0]*lines + new_board, lines

    def analyze_board(self, board, heights):

        holes = 0

        for x in range(BOARD_W):

            seen = False

            for y in range(BOARD_H):

                if board[y] & (1 << x):
                    seen = True
                elif seen:
                    holes += 1

        total_height = sum(heights)
        max_height = max(heights)

        bump = 0
        for i in range(BOARD_W-1):
            bump += abs(heights[i] - heights[i+1])

        return total_height, max_height, holes, bump

    def heuristic(self, board, lines, heights):

        # perfect clear
        if all(row == 0 for row in board):
            return 100000

        # prioridad líneas
        if lines == 4:
            base = 20000
        elif lines == 3:
            base = 8000
        elif lines == 2:
            base = 3000
        elif lines == 1:
            base = 1000
        else:
            base = 0

        total_height, max_height, holes, bump = self.analyze_board(board, heights)

        score = base

        if max_height > 10:
            score -= (max_height - 10) * 400

        # castigar columnas extremadamente altas
        score -= max_height * 50

        # castigar crecimiento total
        score -= total_height * 2

        # agujeros
        score -= holes * 70

        # irregularidad
        score -= bump * 8

        return score

    def beam_search(self, board, queue, beam_width=6, cinco=False):

        search_queue = queue[:5] if cinco else queue[:4]

        states = [(board, [], 0)]

        for piece in search_queue:

            next_states = []

            for b, moves, score in states:

                heights = self.get_heights(b)

                for r, cells in enumerate(self.pieces[piece]):

                    min_x, max_x, _, _ = self.bounds[piece][r]

                    for x in range(-min_x, BOARD_W - max_x):

                        res = self.drop_piece(b, cells, x)
                        if res is None:
                            continue

                        new_board, lines = res

                        new_heights = self.get_heights(new_board)

                        s = score + self.heuristic(new_board, lines, new_heights)

                        next_states.append((new_board, moves + [(piece, x, r)], s))

            next_states.sort(key=lambda x: x[2], reverse=True)
            states = next_states[:beam_width]

            if not states:
                break

        return states[0][1] if states else None

    def generate_keys(self, piece, move):
        x, rot, _ = move
        shape = PIECES[piece][rot]
        min_x, _, _, _ = self.bounds[piece][rot]

        spawn_box = shape.shape[1]
        spawn_x = (BOARD_W - spawn_box)//2 + min_x
        diff = x - spawn_x

        keys = ["up"]*rot

        if diff < 0:
            keys += ["left"] * (-diff)
        else:
            keys += ["right"] * diff

        keys.append("space")
        return keys

    def compute(self, state, cinco=False):

        queue = state["queue"]

        if queue == self.last_queue:
            return None

        self.last_queue = queue.copy()

        multi_moves = self.beam_search(self.board, queue, cinco=cinco)

        if not multi_moves:
            return None

        all_keys = []

        for piece, x, r in multi_moves:

            keys = self.generate_keys(piece, (x, r, None))
            all_keys.extend(keys)

            res = self.drop_piece(self.board, self.pieces[piece][r], x)
            if res:
                self.board, _ = res

        return all_keys

class Environment:

    def __init__(self):

        self.sct = mss.mss()

        self.color_map = {
            (194,115,66):"L",
            (91,74,175):"J",
            (142,191,61):"S",
            (194,63,70):"Z",
            (61,147,114):"I",
            (146,129,61):"C",
            (176,76,166):"T"
        }

        self.zonas = {}

        time.sleep(5)
        self.zonas = self.calibrar_areas()
        print(self.zonas)
        print("Guarde las zonas en la parte de abajo")
        self.listo = False

        # self.zonas["d"] = {'top': 236, 'left': 1231, 'width': 25, 'height': 10}
        # self.zonas["n"] = {'top': 256, 'left': 1155, 'width': 165, 'height': 497}
        # self.listo = True

    def isListo(self):
        return self.listo

    def color_match(self, rgb):

        r,g,b = rgb

        for (cr,cg,cb),p in self.color_map.items():

            if abs(r-cr)<=30 and abs(g-cg)<=30 and abs(b-cb)<=30:

                return p

        return None

    def detectar_next(self, img):

        h, w, _ = img.shape
        slot_h = h // 5

        queue = []

        for i in range(5):

            samples = []

            for dx in [0.25, 0.5, 0.75]:

                y = int((i + 0.6) * slot_h)
                x = int(w * dx)

                b, g, r, _ = img[y, x]

                piece = self.color_match((int(r), int(g), int(b)))

                if piece:
                    samples.append(piece)

            if samples:
                piece = max(set(samples), key=samples.count)
                queue.append(piece)

        return queue
    
    def detectar_death(self, img):

        h, w, _ = img.shape

        for dx in [0.2, 0.5, 0.8]:
            x = int(w * dx)
            y = h // 2

            b, g, r, _ = img[y, x]

            if r < 20 and g < 20 and b < 20:
                return True

        return False

    def calibrar_areas(self):
        with mss.mss() as sct:
            screen = np.array(sct.grab(sct.monitors[0]))

        img = screen.copy()
        clone = img.copy()

        boxes = []
        drawing = False
        x0, y0 = -1, -1

        def mouse(event, x, y, flags, param):
            nonlocal x0, y0, drawing, img

            if event == cv2.EVENT_LBUTTONDOWN:
                drawing = True
                x0, y0 = x, y

            elif event == cv2.EVENT_MOUSEMOVE:
                if drawing:
                    img = clone.copy()
                    cv2.rectangle(img, (x0, y0), (x, y), (0,255,0), 2)

            elif event == cv2.EVENT_LBUTTONUP:
                drawing = False

                x1, y1 = x, y

                left = min(x0, x1)
                top = min(y0, y1)
                width = abs(x1 - x0)
                height = abs(y1 - y0)

                boxes.append({
                    "top": top,
                    "left": left,
                    "width": width,
                    "height": height
                })

                print(f"Zona {len(boxes)}:", boxes[-1])

                img = clone.copy()
                for b in boxes:
                    cv2.rectangle(img,
                                (b["left"], b["top"]),
                                (b["left"]+b["width"], b["top"]+b["height"]),
                                (0,255,0), 2)

        cv2.namedWindow("Selecciona 2 zonas (ENTER para terminar)")
        cv2.setMouseCallback("Selecciona 2 zonas (ENTER para terminar)", mouse)

        while True:
            cv2.imshow("Selecciona 2 zonas (ENTER para terminar)", img)

            key = cv2.waitKey(1) & 0xFF

            if key == 13 or len(boxes) == 2:  # ENTER
                break

        cv2.destroyAllWindows()

        if len(boxes) < 2:
            print("No seleccionaste 2 zonas")
            return None

        return {
            "d": boxes[0],
            "n": boxes[1]
        }

    def percept(self):

        next_img=np.array(self.sct.grab(self.zonas["n"]))
        death_img = np.array(self.sct.grab(self.zonas["d"]))

        queue=self.detectar_next(next_img)
        death = self.detectar_death(death_img)

        return {"queue":queue,"death":death}

def ejecutar_movimiento(keys):
    if keys:
        pyautogui.press(keys)

if __name__=="__main__":

    env=Environment()
    agent=Agent()

    if env.isListo():

        print("=== Tetris Agent ===")

        last_queue=None
        pending_move=None
        primer_mov=True
        ultimo = None

        while True:
            state=env.percept()

            queue=state["queue"]

            if state["death"]:
                with mss.mss() as sct:
                    screenshot = sct.grab(sct.monitors[0])
                    ahora = datetime.now()
                    hora_actual = ahora.strftime("%H_%M_%S")

                    mss.tools.to_png(
                        screenshot.rgb,
                        screenshot.size,
                        output="captura"+hora_actual+".png"
                    )
                break
            
            if len(queue) < 5:
                continue

            if queue!=last_queue:
                if primer_mov:
                    if last_queue is None:
                        ultimo = [queue[-1]]
                    last_queue=queue

                    if pending_move:
                        if primer_mov:
                            primer_mov = False
                        ejecutar_movimiento(pending_move)
                        continue

                    pending_move=agent.compute(state)
                else:
                    state["queue"] = ultimo + state["queue"]
                    ejecutar_movimiento(agent.compute(state, cinco=True))
                    ultimo = [queue[-1]]
                    last_queue=queue