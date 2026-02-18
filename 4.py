from time import sleep
from serial import Serial, SerialException
from threading import Thread
from tkinter import *
from tkinter.font import Font
from PIL import Image, ImageTk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import cv2


sampleC = 8
xk = [i / 20 for i in range(16)]
yk = [0] * 16
xf = list(range(8, 65, 8))
yf = [0] * 16
running, enabledForm1, pulseNorm, allCon, vPlaying = True, True, True, False, False
eMin, eSr, eMax, eCount = 70, 0, 0, 0
vMin, vSr, vMax, vCount = 2, 0, 0, 0
ser, vid = '', ''
calibration_data = []
emg_threshold = 20
calibrated = False

def calibrate_emg(ser_local):
    global emg_threshold, calibration_data, calibrated
    calibration_data = []
    print("Калибровка начата")

    while len(calibration_data) < 200:
        try:
            s = list(map(int, ser_local.readline().decode().strip().split(',')))
            calibration_data.append(s[0])
        except:
            pass

    vals = sorted(set(calibration_data))
    idx = int(len(vals) * 0.6)
    emg_threshold = vals[idx]
    print("Калибровка завершена, порог =", emg_threshold)

    calibrated = True

def readCom():
    global ser, xk, yk, xf, yf, eMin, eSr, eMax, eCount, vMin, vSr, vMax, vCount, pulseNorm, allCon, f, c
    while running:
        wp = 0
        for i in range(1, 30):
            try:
                ser = Serial(f"COM{i}", baudrate=38400)
                calibrate_emg(ser)
                allCon = True
                # c — счётчик сжатий в форме 2
                # form1_state — для детектирования сжатия ещё в форме 1
                c, oldState, form1_state = 0, 0, 0
                ekg_conn.configure(text="Пульс определен, перейдите к подключению\nэлектродов для исследования ЭМГ")
                emg_conn.configure(text="Электроды подключены, для перехода в форму\nисследования необходимо сжать мышцу руки")
                while running:
                    try:
                        s = list(map(int, ser.readline().decode().strip().split(",")))
                    except ValueError:
                        continue

                    # ── Форма 1: ждём сжатия для переключения ──────────────────
                    if enabledForm1:
                        if s[0] < 20:
                            form1_state = 0
                        elif form1_state == 0:
                            # Зафиксировали передний фронт сжатия
                            form1_state = 1
                            # Переключаем форму в главном потоке;
                            # c остаётся 0 — это сжатие НЕ считается первым
                            window.after(0, sw)
                        continue  # пока форма 1 — остальное не обрабатываем

                    # ── Форма 2 ────────────────────────────────────────────────
                    if s[0] < 20:
                        oldState = 0
                    else:
                        if oldState == 0:
                            oldState = 1
                            c += 1
                            if c == 6:
                                puls2.config(text="Исследование закончено,\nпереход к блоку видео")
                                oldState = 1
                                pause()
                                c += 1
                            elif c > 6:
                                pause()
                                if vPlaying:
                                    puls2.config(text="Запуск программы")
                                else:
                                    puls2.config(text="Стоп программы")

                    yk.append((s[1] - 32) / 16)
                    yk.pop(0)
                    xk.append(xk[-1] + 0.05)
                    xk.pop(0)
                    eSr += s[2]
                    eCount += 1
                    if s[2] < eMin:
                        eMin = s[2]
                    elif s[2] > eMax:
                        eMax = s[2]
                    stats1.configure(text=f"Минимальный пульс:{eMin}\nСредний пульс:{int(eSr / eCount)}\nМаксимальный пульс:{eMax}")
                    if 40 < s[2] < 100 and not pulseNorm:
                        pulseNorm = True
                        puls1.configure(text="Пульс в норме")
                        puls2.configure(text="Состояние стабильно")
                    elif (s[2] < 40 or s[2] > 100) and pulseNorm:
                        pulseNorm = False
                        puls1.configure(text="Пульс выходит за пределы нормы")
                        puls2.configure(text="Состояние не стабильно")
                    elif s[2] == 0:
                        puls2.configure(text="Пульс отсутствует")
                        puls2.configure(text="Состояние не стабильно")
                    vAmp = ((s[3] - 32) / 16)
                    vSr += vAmp
                    vCount += 1
                    if vAmp < vMin:
                        vMin = vAmp
                    elif vAmp > vMax:
                        vMax = vAmp
                    stats2.configure(text=f"Минимальные значения ЭМГ:{vMin}\nСредние значения ЭМГ:{int(vSr / vCount)}\nМаксимальные значения ЭМГ:{vMax}")
                    s[4] = s[4] - 140
                    s[5] = s[5] - 60
                    yf = [i / 20 for i in s[4:]]
                    ax1.cla()
                    ax1.set_ylim(-3, 3)
                    ax1.plot(xk, yk, scaley=False)
                    plot1.draw()
                    ax2.cla()
                    ax2.set_ylim(0, 6)
                    ax2.bar(xf, yf, width=7)
                    plot2.draw()
            except SerialException:
                wp += 1
        if wp == 29:
            allCon = False
            wp = 0
            print("Не могу определить COM-порт, проверьте подключение")
            sleep(1)
    try:
        ser.close()
    except BaseException:
        pass

def sw():
    global enabledForm1
    if not enabledForm1:          # защита от двойного вызова
        return
    form1.destroy()
    form2.pack()
    enabledForm1 = False

window = Tk()
window.geometry("960x720")

small = Font(font=("Times New Roman", 14))
big = Font(font=("Times New Roman", 16))
zhir = Font(font=("Times New Roman", 16, "bold"))
ver_sm = Font(font=("Times New Roman", 8))

form1 = Frame(window)

f1grid = Canvas(form1, width=960, height=720)

f1grid.create_rectangle(3, 3, 957, 717)
f1grid.create_rectangle(3, 3, 957, 60)
f1grid.create_rectangle(3, 60, 957, 140)
f1grid.create_rectangle(300, 60, 650, 140)
f1grid.create_rectangle(3, 140, 957, 180)
f1grid.create_rectangle(3, 3, 957, 430)
# f1grid.create_rectangle(550, 200, 930, 410)
# f1grid.create_rectangle(550, 460, 930, 680)

inst1 = ImageTk.PhotoImage(Image.open(r"C:/Users/Ученик 8/Downloads/f/instruction1.png").resize((380, 210)))
Label(f1grid, image=inst1).place(x=550, y=200)
inst2 = ImageTk.PhotoImage(Image.open(r"C:/Users/Ученик 8/Downloads/f/instruction2.png").resize((380, 210)))
Label(f1grid, image=inst2).place(x=550, y=460)

Label(form1, text="Информация о разработчике", font=big).place(x=340, y=14)
Label(form1, text="Инженерно-Технологический\nЛицей", font=big).place(x=20, y=69)
Label(form1, text="Проектирование\nнейроинтерфейсов", font=big).place(x=390, y=69)
Label(form1, text="Рабочее место №5\nТимошенко Андрей Олегович", font=big).place(x=665, y=69)
Label(form1, text="Инструкция для оператора", font=zhir).place(x=340, y=143)
Label(form1, text="Выполнить подключение электродов\nдля исследования ЭКГ согласно примеру:", font=zhir).place(x=20, y=210)
ekg_conn = Label(form1, text="Пульс не определен, проверьте подключение", font=zhir)
ekg_conn.place(x=20, y=330)
Label(form1, text="Выполнить подклчение электродов\nдля исследования ЭМГ согласно примеру:", font=zhir).place(x=20, y=470)
emg_conn = Label(form1, text="Сигнал не определен,  проверьте подключение", font=zhir)
emg_conn.place(x=20, y=580)

Label(form1, text="Выполнить подключение электродов\nдля исследования ЭКГ согласно примеру:", font=zhir).place(x=20, y=210)
Label(form1, text="Пульс определен, перейдите к подключению\nэлектродов для исследования ЭМГ", font=zhir).place(x=20, y=330)
Label(form1, text="Выполнить подклчение электродов\nдля исследования ЭМГ согласно примеру:", font=zhir).place(x=20, y=470)
Label(form1, text="Электроды подключены, для перехода в форму\nисследования нажмите Далее", font=zhir).place(x=20, y=580)

# Button(form1, text="Далее", font=big, command=sw).place(x=15, y=665)

f1grid.pack()

form2 = Frame(window)
f2grid = Canvas(form2, width=960, height=720)

form1.pack()

f2grid.create_rectangle(3, 3, 957, 717)
f2grid.create_rectangle(3, 3, 957, 60)
f2grid.create_rectangle(3, 60, 957, 140)
f2grid.create_rectangle(300, 60, 650, 140)
f2grid.create_rectangle(3, 140, 480, 717)
f2grid.create_rectangle(3, 140, 480, 380)
f2grid.create_rectangle(13, 420, 470, 700)
f2grid.create_rectangle(510, 180, 930, 520)

Label(form2, text="Информация о разработчике", font=big).place(x=340, y=14)
Label(form2, text="Инженерно-Технологический\nЛицей", font=big).place(x=20, y=69)
Label(form2, text="Проектирование\nнейроинтерфейсов", font=big).place(x=390, y=69)
Label(form2, text="Рабочее место №5\nТимошенко Андрей Олегович", font=big).place(x=665, y=69)
Label(form2, text="Информационный блок", font=big).place(x=120, y=383)
Label(form2, text="График ЭКГ", font=big).place(x=60, y=145)
Label(form2, text="График ЭМГ", font=big).place(x=280, y=145)
Label(form2, text="Видео блок", font=big).place(x=660, y=150)
Label(form2, text="Индикатор состояния", font=big).place(x=610, y=530)
puls1 = Label(form2, text="Пульс в норме", font=big)
puls1.place(x=50, y=460)
puls2 = Label(form2, text="Состояние стабильно", font=big)
puls2.place(x=50, y=560)

def pause():
    global vPlaying
    vPlaying = not vPlaying
    if vPlaying:
        puls2.config(text="Запуск программы")
    else:
        puls2.config(text="Стоп программы")


class VideoPlayer:
    def __init__(self, file):
        self.file = file
        self.cap = cv2.VideoCapture(self.file)
        self.delay = int(100 / self.cap.get(cv2.CAP_PROP_FPS))
        self.update()

    def update(self):
        if not vPlaying:
            window.after(self.delay, self.update)
        else:
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self.img = ImageTk.PhotoImage(
                    image=Image.fromarray(frame).resize((412, 310))
                )
                f2grid.create_image(515, 185, image=self.img, anchor=NW)
                window.after(self.delay, self.update)
            else:
                self.cap.release()
                self = VideoPlayer(self.file)

stats1 = Label(
    form2,
    text="Минимальный пульс:\nСредний пульс:\nМаксимальный пульс:",
    justify="left",
    font=ver_sm
)
stats1.place(x=10, y=325)

stats2 = Label(
    form2,
    text="Минимальные значения ЭМГ:\nСредние значения ЭМГ:\nМаксимальные значения ЭМГ:",
    justify="left",
    font=ver_sm
)
stats2.place(x=250, y=325)

f2grid.create_rectangle(515, 570, 635, 690, fill="white", outline="black")
f2grid.create_oval(655, 570, 775, 690, fill="white", outline="black")
f2grid.create_polygon(855, 570, 795, 690, 915, 690, fill="white", outline="black")

fig1, ax1 = plt.subplots()
plot1 = FigureCanvasTkAgg(fig1, form2)
fig1.supylabel('Напряжение, мВ', fontsize=7)
fig1.supxlabel('Время, с', fontsize=7)
ax1.set_position((0.19, 0.19, 0.78, 0.78))
ax1.tick_params(labelsize=5)
plot1._tkcanvas.configure(width=200, height=150)
plot1.get_tk_widget().place(x=10, y=170)

fig2, ax2 = plt.subplots()
plot2 = FigureCanvasTkAgg(fig2, form2)
fig2.supylabel('Амплитуда, мВ', fontsize=7)
fig2.supxlabel('Частота, Гц', fontsize=7)
ax2.set_position((0.19, 0.19, 0.78, 0.78))
ax2.tick_params(labelsize=5)
plot2._tkcanvas.configure(width=200, height=150)
plot2.get_tk_widget().place(x=250, y=170)

f2grid.pack()

t = Thread(target=readCom)
t.start()

def z():
    global vid
    while vid == "":
        try:
            vid = VideoPlayer("test.mp4")
        except BaseException:
            sleep(1)


goyda = Thread(target=z)
goyda.start()

while not calibrated:
    sleep(0.05)

window.mainloop()
running = False

try:
    ser.close()
except:
    pass
