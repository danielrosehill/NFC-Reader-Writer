The purpose of this repo is to create a fully functional application/GUI for reading and writing NFC tags. 

I use NFC tags of type NTAG213 with an ACR122U USB reader (attached to my computer permanently)

I self host an inventory management system called Homebox and use NFC tags to record inventory information on physical assets - like computer parts.

The UI should support both reading and writing with separate tabs. When you move from reading to writing, the reading loop should be closed - and vice versa.

Here are desired functionalities for both sets of features.

## Read

The NFC tags will contain asset links to Homebox. Here's a real one:

https://homebox.residencejlm.com/item/93ef143e-e4dd-4f39-a565-b827c1f044e0

As you can see, they are long links.

Sometimes the asset tags will be in the old format like this:

http://10.0.0.1:3100//item/93ef143e-e4dd-4f39-a565-b827c1f044e0

they may also be:

https://10.0.0.3100/item/foo

Or 

https://10.0.0.x:3100/item/foo

The reader should support rewrite logic so that http://10.0.0.1:3100/item/* is rewritten to https://homebox.residencejlm.com/item/* 

The URLs should be:

- Detected 
- Opened automatically in Google Chrome (syntax: chrome url).

## Writing 

For writing tags: I always lock them (these are cheap single use NFC tags for inventory.)

So desired function is:

-> User pastes URL 
-> User selects "Write & Lock" 
-> When an empty tag is presented to the NFC reader/writer, in a single operation, the tag is written and then locked 

It would also be useful to support batch operations for writing: I might occasionaly need to create 5 or 6 tags with the same URL. 

## General Functionalities 

Clean UI

Easy support for fast efficient inventory operations 

## Other Details

This is a private app for use on my own computer. 

I will sometimes want to add features. So an easy update process is also key.

Repo should have a script for:

-> Build new debian package, append new version number  
-> Update existing package 