# eBallot – Online Voting System

**eBallot** is a secure and user-friendly online voting platform, developed as part of a Master’s thesis at the International Hellenic University.  
It is built with **Django** and focuses on providing anonymity, integrity, and transparency in electronic elections.

---

## 🔎 Introduction

Traditional election processes often face challenges such as lack of transparency, logistical difficulties, and potential vulnerabilities to fraud.  
**eBallot** addresses these issues by providing a modern, digital solution that ensures **anonymity, security, and prevention of double voting**, while remaining simple and accessible to both administrators and voters.

This project was developed as part of the **Master’s Thesis in Applied Informatics (2025)**.

---

## 📚 Motivation & Background

- Traditional voting methods are costly and time-consuming.  
- Electronic voting systems must guarantee anonymity, integrity, and trust.  
- Existing e-voting solutions often face challenges in user adoption and security.  
- **eBallot** provides a lightweight, extensible, and secure voting framework that can be used in academic, organizational, or small-scale governmental elections.  

---

## 🚀 Features

- User Registration & Authentication  
- Creation and Management of Elections (Admin panel)  
- Anonymous Vote Casting with hashing receipts (salted hashes)  
- Prevention of Double Voting  
- Real-time Results Visualization with **Chart.js**  
- Demographic Analysis (age, gender, region)  
- Receipt Hashes for vote verification  
- Role-based Access (Admin / Voter)  
- Demo commands for quick setup  

---

## 🏗️ Architecture Overview

The system is structured around the **Django framework** with clear separation of responsibilities:

- **Backend (Django / Python)** – core logic, models, vote handling  
- **Database (SQLite default)** – stores election data and user profiles  
- **Frontend (Bootstrap, SCSS, JavaScript)** – user interface and interactivity  
- **Visualization (Chart.js)** – election results, statistics, demographics  
- **Security Layer** – hashing receipts, salted hashes, prevention of duplicate voting  

---

## 🔐 Security Features

- **Anonymous voting**: separation of voter identity from vote record.  
- **Vote receipts**: each vote is linked to a salted hash receipt for verification.  
- **Double-voting prevention**: system enforces one vote per user per election.  
- **Role-based access control**: strict separation between admins and voters.  

---

## 👥 User Roles

- **Administrator**
  - Create, configure, and manage elections  
  - View results and demographics  
  - Manage voter access and permissions  

- **Voter**
  - Register and log in securely  
  - Participate in available elections  
  - Cast votes anonymously  
  - Receive vote receipt for verification  
  - View published results  

---

## 🛠️ Technologies

- **Backend**: Django (Python 3.11)  
- **Database**: SQLite (default) – PostgreSQL/MySQL supported  
- **Frontend**: HTML5, CSS3, Bootstrap 5, SCSS  
- **Visualization**: Chart.js, Swiper, Glightbox  
- **Other Tools**: Django management commands (`demo`, `purge`)  

---


