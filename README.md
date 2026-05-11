# ArFetch - Artix Linux Fetch
---

### What's the difference from fastfetch?
ArFetch has many differences including:
- Exclusive to Artix Linux
- Shows what init system you're using *(+ how many active services)*
- shows core **AND** thread count
- Made in Python (which is **COOL**)

---

### Example
![example1](https://raw.githubusercontent.com/ColinZeDev/arfetch/refs/heads/main/DWM_2026-05-11_17-51-51.png)
(**NOT** the default colors, just my config)

---

### Usage
- `arfetch` Displays the info
- `arfetch -v|--version` Prints version

---

### Installation
ArFetch is on the AUR, so to install it simply just install the `arfetch-bin` package with your AUR helper of choice.
**Example:**
```sh
yay -S arfetch-bin
```

---

#### * **If anything is broken (like the init system stuff cause I only know the OpenRC one works) pleak make an issue post or something)**
