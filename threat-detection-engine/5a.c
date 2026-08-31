#include<stdio.h>
#include<stdlib.h>
struct node
{
    int info;
    struct node*next;
    struct node*prev;
};
struct node* createNode(int data,struct node*h)
{
    struct node*newNode;
    newNode=(struct node*)malloc(sizeof(struct node));
    newNode->info=data;
    newNode->next=NULL;
    newNode->prev=NULL;
    if(h==NULL)
    {
       h=newNode;
       return h; 
    }
    struct node*temp;
    temp=h;
    while(temp->next!=NULL)
    {
        temp=temp->next;
    }
    temp->next=newNode;
    newNode->prev=temp;
    return h;
}
struct node* insertAtEnd(int data,struct node*h)
{
    h=createNode(data,h);
    return h;
}
struct node* deleteAtEnd(struct node*h)
{
    struct node*temp,*prev;
    if(h==NULL)
    {
        printf("\nEmpty List\n");
        return h;
    }
    temp=h;
    prev=NULL;
    while(temp->next!=NULL)
    {
        prev=temp;
        temp=temp->next;
    }
    if(prev==NULL)       // only one node
    {
        h=NULL;
    }
    else
    {
        prev->next=NULL;
    }
    free(temp);
    printf("\nNode Deleted\n");
    return h;
}
struct node* insertAtPos(int pos,int data,struct node*h)
{
    if(h==NULL)
    {
        printf("Empty List\n");
        return h;
    }
    struct node*n=createNode(data,NULL);
    struct node*temp,*pre;
    if(pos==1)
    {
        n->next=h;
        h->prev=n;
        h=n;

        printf("\nNode Inserted\n");
        return h;
    }
    temp=h;
    pre=NULL;
    for(int i=1;i<pos;i++)
    {
        pre=temp;
        temp=temp->next;

        if(temp==NULL && i<pos-1)
        {
            printf("\nInvalid Position\n");
            free(n);
            return h;
        }
    }
    if(temp==NULL)
    {
        printf("\nInvalid Position\n");
        free(n);
        return h;
    }
    n->next=temp;
    n->prev=pre;
    pre->next=n;
    temp->prev=n;
    printf("\nNode Inserted\n");
    return h;
}
