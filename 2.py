from time import sleep, time
from serial import Serial, SerialException
from threading import Thread
from tkinter import *
from tkinter.font import Font
from PIL import Image, ImageTk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

sampleC = 8
xk = [i / 20 for i in range(16)]
yk = [0] * 16
xf = list(range(8, 65, 8))
yf = [0] * 16
running, enabledForm1, pulseNorm, allCon = True, True, False, False
eMin, eSr, eMax, eCount = 70, 0, 0, 0
vMin, vSr, vMax, vCount = 2, 0, 0, 0
ser = ""

# --- Состояния подключения ---
# 0 = ничего, 1 = ЭКГ определён, 2 = ЭМГ определён (готов к сжатию), 3 = переход
connect_state = 0

# Буфер для определения стабильного пульса
ecg_stable_buf = []   # последние N значений пульса
emg_calib_buf  = []   # значения ЭМГ во время калибровки
emg_baseline   = None # среднее ЭМГ в покое
emg_calib_done = False
emg_calib_start = None

CALIB_TIME   = 3.0   # секунд на калибровку ЭМГ после обнаружения ЭКГ
SQUEEZE_MULT = 2.5   # во сколько раз выше базовой линии считается сжатием
SQUEEZE_HOLD = 3     # сколько подряд пакетов с высоким ЭМГ = сжатие
squeeze_count = 0

def is_ecg_valid(pulse, amplitude):
    """ЭКГ считается подключённым если пульс реалистичен И есть сигнал"""
    return 45 <= pulse <= 95 and amplitude >= 3

def readCom():
    global ser, xk, yk, xf, yf, eMin, eSr, eMax, eCount
    global vMin, vSr, vMax, vCount, pulseNorm, allCon
    global connect_state, ecg_stable_buf, emg_calib_buf
    global emg_baseline, emg_calib_done, emg_calib_start
    global squeeze_count

    while running:
        wp = 0
        for i in range(1, 30):
            try:
                ser = Serial(f"COM{i}", baudrate=38400)
                allCon = True
                c, oldState = 0, 0

                # Сброс состояния при новом подключении
                connect_state = 0
                ecg_stable_buf.clear()
                emg_calib_buf.clear()
                emg_baseline = None
                emg_calib_done = False
                emg_calib_start = None
                squeeze_count = 0

                while running:
                    try:
                        s = list(map(int, ser.readline().decode().strip().split(",")))
                    except ValueError:
                        continue

                    if not enabledForm1:
                        # ---- Графики ----
                        if s[0] < 20:
                            oldState = 0
                        else:
                            if oldState == 0:
                                oldState = 1
                                c += 1
                                if c == 6:
                                    puls2.configure(text="Исследование закончено\nпереход к блоку видео")

                        yk.append((s[1] - 32) / 16)
                        yk.pop(0)
                        xk.append(xk[-1] + 0.05)
                        xk.pop(0)

                        eSr += s[2]
                        eCount += 1
                        if s[2] < eMin: eMin = s[2]
                        elif s[2] > eMax: eMax = s[2]
                        stats1.configure(text=f"Минимальный пульс:{eMin}\nСредний пульс:{int(eSr/eCount)}\nМаксимальный пульс:{eMax}")

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

                        vAmp = (s[3] - 32) / 16
                        vSr += vAmp
                        vCount += 1
                        if vAmp < vMin: vMin = vAmp
                        elif vAmp > vMax: vMax = vAmp
                        stats2.configure(text=f"Минимальные значения ЭМГ:{vMin}\nСредние значения ЭМГ:{int(vSr/vCount)}\nМаксимальные значения ЭМГ:{vMax}")

                        yf = [i / 20 for i in s[4:]]
                        ax1.cla(); ax1.set_ylim(-3, 3); ax1.plot(xk, yk, scaley=False); plot1.draw()
                        ax2.cla(); ax2.set_ylim(0, 6); ax2.bar(xf, yf, width=7); plot2.draw()

                    else:
                        # ---- Форма 1: определение подключения ----
                        pulse     = s[2]
                        amplitude = s[0]   # размах ЭКГ
                        emg_raw   = s[1]   # сырое ЭМГ

                        # --- Шаг 1: ждём стабильного ЭКГ ---
                        if connect_state == 0:
                            if is_ecg_valid(pulse, amplitude):
                                ecg_stable_buf.append(pulse)
                            else:
                                ecg_stable_buf.clear()  # сброс при ненадёжном сигнале

                            if len(ecg_stable_buf) >= 8:
                                # 8 пакетов подряд с нормальным пульсом
                                connect_state = 1
                                emg_calib_start = time()
                                ecg_stable_buf.clear()
                                ekg_conn.configure(text="✓ Пульс определён")

                        # --- Шаг 2: калибруем базовую линию ЭМГ ---
                        elif connect_state == 1:
                            elapsed = time() - emg_calib_start
                            if elapsed < CALIB_TIME:
                                emg_calib_buf.append(emg_raw)
                                # Показываем обратный отсчёт
                                remaining = int(CALIB_TIME - elapsed) + 1
                                emg_conn.configure(text=f"Калибровка ЭМГ... не двигайте рукой ({remaining}с)")
                            else:
                                if emg_calib_buf:
                                    emg_baseline = sum(emg_calib_buf) / len(emg_calib_buf)
                                    connect_state = 2
                                    emg_conn.configure(text="✓ ЭМГ откалиброван\nСожмите кулак для начала")
                                else:
                                    # Нет данных — начать заново
                                    connect_state = 0

                        # --- Шаг 3: ждём сжатия кулака ---
                        elif connect_state == 2:
                            threshold = emg_baseline * SQUEEZE_MULT + 5  # +5 для защиты от нуля
                            if emg_raw > threshold:
                                squeeze_count += 1
                            else:
                                squeeze_count = 0  # сброс если сигнал упал

                            if squeeze_count >= SQUEEZE_HOLD:
                                connect_state = 3
                                # Переход выполняется в главном потоке
                                window.after(0, sw)

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
    if not enabledForm1:
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

'''
Label(form1, text="Выполнить подключение электродов\nдля исследования ЭКГ согласно примеру:", font=zhir).place(x=20, y=210)
Label(form1, text="Пульс определен, перейдите к подключению\nэлектродов для исследования ЭМГ", font=zhir).place(x=20, y=330)
Label(form1, text="Выполнить подклчение электродов\nдля исследования ЭМГ согласно примеру:", font=zhir).place(x=20, y=470)
Label(form1, text="Электроды подключены, для перехода в форму\nисследования нажмите Далее", font=zhir).place(x=20, y=580)
'''

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

while not allCon:
    pass

window.mainloop()
running = False

try:
    ser.close()
except:
    pass
