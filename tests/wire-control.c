/* SPDX-License-Identifier: BSD-3-Clause */
/* Test guest helper: send exactly one stdin datagram, with no token logging. */
#include <arpa/inet.h>
#include <stdlib.h>
#include <unistd.h>
int main(int argc,char **argv) {
  struct sockaddr_in peer={.sin_family=AF_INET};char buf[128];
  if(argc!=3 || inet_pton(AF_INET,argv[1],&peer.sin_addr)!=1)return 2;
  peer.sin_port=htons(atoi(argv[2]));
  int fd=socket(AF_INET,SOCK_DGRAM,0);ssize_t n=read(0,buf,sizeof(buf));
  if(fd<0 || n<=0)return 3;
  ssize_t sent=sendto(fd,buf,n,0,(struct sockaddr *)&peer,sizeof(peer));close(fd);
  return sent==n?0:4;
}
