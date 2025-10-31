Public key for testnet address
Asked 7 years, 9 months ago
Modified 7 years, 9 months ago
Viewed 4k times

Report this ad
1

I'm trying to create a transaction on the testnet (manually). I have the following private key: cQKqSNkEdyLJziQSr4iKTUJC95s9HHFo4bY88gi2i6v2quiVVLZb which belongs to the following public address: mkhn3gfrGHmd4b1ZmHLdMsbQd2eHRKg8wN. When I try to sign the transaction, the public (uncompressed) key that I generate, is: 042d7331345e0da6ab1125eb39488a542a9923f31c585c20114d211a9f6bc9f3bf55d1d843cb7cf1d36b32d1cb00d2f140ef028e726a19a766f6ca7cef7b956583. This turns out to be invalid (because the transaction gets rejected by the network). However, when I tried using a tool for signing the transaction, it generated the following (correct) public key: 040b4a4274222d7239d33c17ce39d753eee97103773b7e5a89e62f0ef0121032d7331345e0da6ab1125eb39488a542a9923f31c585c20114d211a9f6bc9f3b.

What is the difference between these keys? How come the first one is incorrect when signing the tx but correct when I generated the public address for it?

testnet
Share
Improve this question
Follow
asked Jan 2, 2018 at 8:04
user2298995's user avatar
user2298995
19333 silver badges1414 bronze badges
Add a comment
1 Answer
Sorted by:

Highest score (default)
3

Some observations: the priv key matches with the first compressed address (mkhn3...). It fits to the pubkey in hex, see below. The way keys are derived is described here - see also the picture. http://www.righto.com/2014/02/bitcoins-hard-way-using-raw-bitcoin.html

enter image description here

Once you have the pubkey in hex, there are 8 following steps to come to the final bitcoin address:

1 - Public ECDSA Key
2 - SHA-256 hash of 1
3 - RIPEMD-160 Hash of 2
4 - Adding network bytes to 3
5 - SHA-256 hash of 4
6 - SHA-256 hash of 5
7 - First four bytes of 6
8 - Adding 7 at the end of 4
9 - Base58 encoding of 8
The first uncompressed pubkey (which fits to the privkey):

042d7331345e0da6ab1125eb39488a542a9923f31c585c20114d211a9f6bc9f3bf55d1d843cb7cf1d36b32d1cb00d2f140ef028e726a19a766f6ca7cef7b956583

would convert into this bitcoin address:

myfp2YcyYjksxmdfA74yEuBmaUgt9xWCot
and your second uncompressed pubkey

040b4a4274222d7239d33c17ce39d753eee97103773b7e5a89e62f0ef0121032d7331345e0da6ab1125eb39488a542a9923f31c585c20114d211a9f6bc9f3b

would convert to this bitcoin address:

mmKUwoRgd9YdvRYYXGyumjduRMTAPCnkMz
I am not sure which tools you used to create your keys, it looks like you have somewhere a gap between using compressed and uncompressed keys. A very good reference is in the online book from Andreas ("Mastering Bitcoin, 2nd edition"), which is also online readable (see chapter 4...).

Share
Improve this answer
Follow
answered Jan 2, 2018 at 9:57
pebwindkraft's user avatar
pebwindkraft
5,19622 gold badges1515 silver badges3434 bronze badges
Thank you for your responses, you've been very helpful with my questions. I will look into the online book hoping it will provide me better understanding. However, following the procedures you mentioned (which is what I've been doing so far), generates a single pubkey, what is the process for generating the second one? – 
user2298995
 CommentedJan 2, 2018 at 11:02
Now I got it, seems like I misunderstood your point. How can an uncompressed pubkey and a compressed pubkey result in the same public address? – 
user2298995
 CommentedJan 2, 2018 at 12:36
2
compressed and uncompressed pubkeys never result in the same address. The root is the hex private key (64 hexadecimal digits). From this you can create a WIF encoded key, and depending on the prefix, you get a key starting with "5", or with "L" or "K". The process is well described in Andreas' book. When creating the pubkeys, there are uncompressed pubkeys for WIF keys starting with "5", the others would create compressed pubkeys. – 
pebwindkraft
 CommentedJan 2, 2018 at 14:28
2
Summary: with the same private key you can create compressed or uncompressed WIF keys (a representation of hex keys), and from there create the two pubkeys, which can be converted into two different bitcoin addresses. Though both addresses (and keys) are based on the same priv key, they are not "interchangeable". In Bitcoin they lead to completly different addresses. – 
pebwindkraft
 CommentedJan 2, 2018 at 14:31
