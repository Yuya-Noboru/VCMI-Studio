# Heroes III VCMI Studio
VCMI Studio is an all-in-one modding suite for Heroes 3 VCMI by Yūya Noboru.
It is designed to help modders in various ways : from JSON configuration file generation to sprite editing.

The app has several independent tabs which all serve different purposes (tab names are pretty explicit).

## Features
### Sprite Editor
![Sprite Editor image](https://forum.vcmi.eu/uploads/default/original/2X/f/f54bda6dda6852d2987b98f89cd495f23aefcb3d.png)

The Sprite Editor is directly inspired by DEF tool, and allows you to manage frame sequences with a similar real-time playback.

It also comes with an automated 256-color palette generation and bulk HSL color adjustments to easily recolor your sprites. You can also remove the cyan background in a few clicks.

You can import/export projects and color palettes. “Generate JSON” generates the animation’s JSON file.

### Creature configuration
![Creature configuration image1](https://forum.vcmi.eu/uploads/default/original/2X/3/337845f7406e3d9c11f4be64c4311ab29a6f472f.png)
![Creature configuration image2](https://forum.vcmi.eu/uploads/default/original/2X/3/315928e44a1a8fdd534c6d3eb9658d458e3ef1c1.png)

Allows you to create creature configuration files. You just have to fill the stats and other data needed, then press “Generate JSON”.

It comes with a text editor so you can manually edit the JSON on-the-go.

### Townscreen
![Townscreen Editor image](https://forum.vcmi.eu/uploads/default/original/2X/f/f2a5c0cf3512bc470715517b1a9ce3fe73a8141c.png)

This townscreen tool lets you bulk-remove backgrounds, and generate building area and building border sprites.
There’s a built-in mask editor so you can draw the area/border. You can change sprite opacity to help you do so.


## Install
1) [Download](https://github.com/Yuya-Noboru/VCMI-Studio/archive/refs/heads/main.zip) the code and extract the .ZIP file anywhere you want.
2) Install the requirements :
- ```PILLOW ≥ v9.0.0```
- ```PyGame ≥ v2.0.0```
  
3) Launch ```VCMI_Studio.py```
