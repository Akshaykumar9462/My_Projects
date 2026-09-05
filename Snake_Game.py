
from tkinter import *
import random
GAME_WIDTH=1100
GAME_HEIGHT=550
SPEED=150
current_speed=SPEED
SPACE_SIZE=50
BODY_PARTS=3
SNAKE_COLOUR="#0400FF"
FOOD_COLOUR="#F1E9E9"
BACKGROUND_COLOUR="#000000"
import json
def save_scores(scores):
    with open("scores.json", "w") as f:
        json.dump(scores, f)
def load_scores():
    try:
        with open("scores.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return [] 
import json

def load_scores():
    try:
        with open("scores.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_scores(scores):
    with open("scores.json", "w") as f:
        json.dump(scores, f)
class Snake:
    def __init__(self):
        self.body_size=BODY_PARTS
        self.coordinates=[]
        self.squares=[]
        for i in range(0,BODY_PARTS):
            self.coordinates.append([0,0])
        for i, (x, y) in enumerate(self.coordinates):
            color = "#00FFAA" if i == 0 else SNAKE_COLOUR  # brighter head
            square = canvas.create_rectangle(x, y, x+SPACE_SIZE, y+SPACE_SIZE, fill=color, tag="snake")
            self.squares.append(square)

class Food:
    def __init__(self):
        x=random.randint(0,(GAME_WIDTH//SPACE_SIZE)-1)*SPACE_SIZE
        y=random.randint(0,(GAME_HEIGHT//SPACE_SIZE)-1)*SPACE_SIZE
        self.coordinates=[x,y]
        canvas.create_oval(x+4, y+4, x+SPACE_SIZE+4, y+SPACE_SIZE+4, fill="#333333", outline="", tag="food")
        canvas.create_oval(x, y, x+SPACE_SIZE, y+SPACE_SIZE, fill=FOOD_COLOUR, tag="food")

def next_turn(snake, food):
    x, y = snake.coordinates[0]
    if direction == "up":
        y -= SPACE_SIZE
    elif direction == "down":
        y += SPACE_SIZE
    elif direction == "left":
        x -= SPACE_SIZE
    elif direction == "right":
        x += SPACE_SIZE
    snake.coordinates.insert(0, (x, y))
    square = canvas.create_rectangle(x, y, x+SPACE_SIZE, y+SPACE_SIZE, fill="#00FFAA")
    snake.squares.insert(0, square)
    if len(snake.squares) > 1:
        canvas.itemconfig(snake.squares[1], fill=SNAKE_COLOUR)

    global current_speed
    if x == food.coordinates[0] and y == food.coordinates[1]:
        global score
        score += 1
        label.config(text="Score:{}".format(score))
        canvas.delete("food")
        food = Food()
        if score % 3 == 0 and current_speed > 60:
            current_speed -= 10
    else:
        del snake.coordinates[-1]
        canvas.delete(snake.squares[-1])
        del snake.squares[-1]

    if check_collision(snake):
        game_over()
    else:
        window.after(current_speed, next_turn, snake, food)


def change_direction(new_direction):
    global direction
    if new_direction=='left':
        if direction!='right':
            direction=new_direction
    if new_direction=='right':
        if direction!='left':
            direction=new_direction
    if new_direction=='up':
        if direction!='down':
            direction=new_direction
    if new_direction=='down':
        if direction!='up':
            direction=new_direction

def check_collision(snake):
    x,y=snake.coordinates[0]
    if x<0 or x>=GAME_WIDTH:
        print("Game Over")
        return True    
    elif y<0 or y>=GAME_HEIGHT:
        print("Game Over")
        return True  
    for body_part in snake.coordinates[1:]:
        if x==body_part[0] and y==body_part[1]:
            print("Game Over")
            return True
    return False
def game_over():
    scores = load_scores()
    scores.append(score)
    scores.sort(reverse=True)
    scores = scores[:5]
    save_scores(scores)
    canvas.delete(ALL)
    canvas.create_text(canvas.winfo_width()/2, canvas.winfo_height()/2 - 140,
                    font=("Calibri", 70), text="Game Over", fill="red", tag="gameover")

    leaderboard_text = "Top Scores:\n" + "\n".join(str(s) for s in scores)
    canvas.create_text(canvas.winfo_width()/2, canvas.winfo_height()/2 + 20,
                    font=("Calibri", 20), text=leaderboard_text, fill="white")

    restart_button = Button(window, text="Play Again", font=("Calibri", 20), command=restart_game)
    canvas.create_window(canvas.winfo_width()/2, canvas.winfo_height()/2 + 180, window=restart_button)
def restart_game():
    global score, direction, current_speed, snake, food
    canvas.delete(ALL)
    canvas.create_rectangle(2, 2, GAME_WIDTH-2, GAME_HEIGHT-2, outline="#0400FF", width=3)
    score = 0
    direction = 'down'
    current_speed = SPEED
    label.config(text='Score:{}'.format(score))
    snake = Snake()
    food = Food()
    next_turn(snake, food)
window=Tk()
window.title("Snake game")
window.resizable(False,False)
score=0
direction='down'
label=Label(window,text='Score:{}'.format(score),font=('Calibri'))
label.pack()
canvas=Canvas(window,bg=BACKGROUND_COLOUR,height=GAME_HEIGHT,width=GAME_WIDTH)
canvas.pack()
canvas.create_rectangle(2, 2, GAME_WIDTH-2, GAME_HEIGHT-2, outline="#0400FF", width=3)
window.update()
window_width=window.winfo_width()
window_height=window.winfo_height()
screen_width=window.winfo_screenwidth()
screen_height=window.winfo_screenheight()
x=int((screen_width/2)-(window_width/2))
y=int((screen_height/2)-(window_height/2))
window.geometry(f"{window_width}x{window_height}+{x}+{y}")
window.bind('<Left>',lambda event:change_direction('left'))
window.bind('<Right>',lambda event:change_direction('right'))
window.bind('<Up>',lambda event:change_direction('up'))
window.bind('<Down>',lambda event:change_direction('down'))
snake=Snake()
food=Food()
next_turn(snake,food)
